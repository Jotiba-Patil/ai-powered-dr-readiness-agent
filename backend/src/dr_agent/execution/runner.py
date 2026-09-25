"""Runs approved steps one at a time: main call, then verify call.

Each loop iteration picks one call under the execution's lock, marks it
started and saves (so a restart finds it `RUNNING` and turns it `UNKNOWN`),
calls the tool without holding the lock, then applies the outcome under the
lock again. A result that arrives after an abort is recorded but changes no
state. Calls are never retried automatically (ADR 0006).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from dr_agent.execution.approvals import is_approved
from dr_agent.execution.call_records import Outcome, begin_call, finish_call, record_late_result
from dr_agent.execution.canonical import call_hash
from dr_agent.execution.journal import SYSTEM_ACTOR, Journal
from dr_agent.execution.models import (
    CallKind,
    ExecutionMode,
    ExecutionState,
    StepRun,
    StepState,
    ToolCall,
)
from dr_agent.execution.policy import Catalog
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.execution.session import ExecutionLimits, Sessions
from dr_agent.execution.step_calls import evaluate_step_calls
from dr_agent.execution.transitions import (
    SATISFIED_STEP_STATES,
    TERMINAL_STEP_STATES,
    ExecutionEvent,
    StepEvent,
)
from dr_agent.tools.base import ToolExecutor
from dr_agent.utils.errors import AppError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.execution.runner")
_MAX_ERROR = 500


class StepRunner:
    def __init__(
        self,
        sessions: Sessions,
        executors: Mapping[ExecutionMode, ToolExecutor],
        policy: ExecutionPolicy,
        limits: ExecutionLimits,
    ) -> None:
        self._sessions = sessions
        self._executors = dict(executors)
        self._policy = policy
        self._limits = limits

    async def run_until_blocked(self, execution_id: str, catalog: Catalog) -> None:
        while True:
            async with self._sessions.open(execution_id) as journal:
                picked = self._pick(journal, catalog)
                mode = journal.execution.mode
            if picked is None:
                return
            step_number, call = picked
            outcome = await self.invoke(call, mode)
            async with self._sessions.open(execution_id) as journal:
                if not self._apply(journal, step_number, call.kind, outcome):
                    return

    async def invoke(self, call: ToolCall, mode: ExecutionMode) -> Outcome:
        """Dry runs go to the dry-run executor, live runs to the real one."""
        timeout = self._limits.tool_timeout_seconds
        try:
            result = await asyncio.wait_for(
                self._executors[mode].call_tool(
                    call.server, call.tool, call.arguments, timeout_seconds=timeout
                ),
                timeout=timeout,
            )
        except TimeoutError:
            return Outcome(ok=False, error=f"timed out after {timeout:g} s")
        except AppError as exc:
            return Outcome(ok=False, error=exc.message[:_MAX_ERROR])
        except Exception as exc:  # an executor bug must not leave the step RUNNING forever
            _log.warning("tool_executor_crashed", tool=call.tool, error_type=type(exc).__name__)
            return Outcome(ok=False, error=f"executor error: {type(exc).__name__}")
        error = None if result.ok else (result.content[:_MAX_ERROR] or "the tool reported failure")
        return Outcome(ok=result.ok, result=result, error=error)

    def _pick(self, journal: Journal, catalog: Catalog) -> tuple[int, ToolCall] | None:
        execution = journal.execution
        if execution.state is not ExecutionState.RUNNING or self._paused_for_wait(journal):
            return None
        if all(run.state in TERMINAL_STEP_STATES for run in execution.steps):
            journal.move_execution(ExecutionEvent.COMPLETE, SYSTEM_ACTOR)
            return None
        for run in execution.steps:
            call = self._runnable_call(journal, run, catalog)
            if call is None:
                continue
            if execution.tool_calls_used >= self._limits.max_tool_calls:
                journal.move_execution(
                    ExecutionEvent.PAUSE, SYSTEM_ACTOR, "tool call limit reached"
                )
                return None
            if call.kind is CallKind.MAIN:
                journal.move_step(run, StepEvent.START, SYSTEM_ACTOR)
            begin_call(journal, run, call, SYSTEM_ACTOR)
            return run.step_number, call.model_copy(deep=True)
        return None

    def _runnable_call(self, journal: Journal, run: StepRun, catalog: Catalog) -> ToolCall | None:
        if run.state is StepState.VERIFYING and run.verify and run.verify.started_at is None:
            return run.verify
        if run.state is not StepState.APPROVED or run.call is None:
            return None
        satisfied = {
            r.step_number for r in journal.execution.steps if r.state in SATISFIED_STEP_STATES
        }
        if not set(run.depends_on) <= satisfied:
            return None
        # Re-check right before running: policy, the hash of what runs, and the approvals.
        problems = evaluate_step_calls(run, self._policy, catalog)
        intact = run.call.call_hash == call_hash(run.call.server, run.call.tool, run.call.arguments)
        if problems or not intact or not is_approved(run.call, run.verify):
            run.policy_errors = problems
            run.call.approvals = []
            journal.move_step(
                run, StepEvent.EDIT, SYSTEM_ACTOR, "approval no longer valid; approve again"
            )
            return None
        return run.call

    def _paused_for_wait(self, journal: Journal) -> bool:
        limit = self._limits.approval_timeout
        for run in journal.execution.steps:
            if run.waiting_since is not None and journal.now - run.waiting_since > limit:
                minutes = f"{limit.total_seconds() / 60:g}"
                reason = f"step {run.step_number} waited more than {minutes} minutes for a person"
                journal.move_execution(ExecutionEvent.PAUSE, SYSTEM_ACTOR, reason)
                return True
        return False

    def _apply(self, journal: Journal, step_number: int, kind: CallKind, outcome: Outcome) -> bool:
        """Records the outcome; returns whether the loop should look for the next call."""
        run = journal.execution.step(step_number)
        call = run.call if kind is CallKind.MAIN else run.verify
        expected = StepState.RUNNING if kind is CallKind.MAIN else StepState.VERIFYING
        if call is None or run.state is not expected or call.finished_at is not None:
            record_late_result(journal, step_number, kind, outcome)
            return False
        finish_call(journal, run, call, outcome)
        if outcome.ok:
            event = StepEvent.CALL_SUCCEEDED if kind is CallKind.MAIN else StepEvent.VERIFY_PASSED
            journal.move_step(run, event, SYSTEM_ACTOR)
            return True
        event = StepEvent.CALL_FAILED if kind is CallKind.MAIN else StepEvent.VERIFY_FAILED
        journal.move_step(run, event, SYSTEM_ACTOR, outcome.error)
        if journal.execution.state is ExecutionState.RUNNING:
            journal.move_execution(ExecutionEvent.PAUSE, SYSTEM_ACTOR, f"step {step_number} failed")
        return False
