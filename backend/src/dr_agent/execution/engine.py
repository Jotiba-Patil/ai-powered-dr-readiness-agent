"""`ExecutionEngine`: the one entry point the API and CLI use for executions.

Every public method enforces the safety switches (ADR 0006), then works on the
stored execution through a `Session`, so each request is one transaction of
state plus audit events. Tool calls happen only in `advance()` and `rollback()`,
one at a time per execution.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import uuid4

from dr_agent.execution.audit import AuditEvent, ChainVerification, verify_chain
from dr_agent.execution.decisions import Decision, apply_decision
from dr_agent.execution.models import AnalysisRef, Execution, ExecutionMode, ExecutionState
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.execution.proposer import ToolProposer, propose_missing
from dr_agent.execution.recovery import interrupt_in_flight
from dr_agent.execution.rollback import run_rollback
from dr_agent.execution.runner import StepRunner
from dr_agent.execution.session import ExecutionLimits, Sessions
from dr_agent.execution.step_actions import require_text
from dr_agent.execution.store import ExecutionStore
from dr_agent.execution.transitions import TERMINAL_EXECUTION_STATES, ExecutionEvent
from dr_agent.models.runbook import Runbook
from dr_agent.tools.base import ToolExecutor
from dr_agent.utils.errors import (
    CapacityError,
    ConflictError,
    ExecutionDisabledError,
    InvalidTransitionError,
)

_ACTIVE = (ExecutionState.RUNNING, ExecutionState.PAUSED)


class ExecutionEngine:
    def __init__(
        self,
        *,
        store: ExecutionStore,
        executor: ToolExecutor,
        policy: ExecutionPolicy,
        limits: ExecutionLimits,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: uuid4().hex,
        proposer: ToolProposer | None = None,
        dry_run_executor: ToolExecutor | None = None,
    ) -> None:
        self._store, self._executor, self._policy = store, executor, policy
        self._limits, self._clock, self._id_factory = limits, clock, id_factory
        self._sessions = Sessions(store, clock)
        executors = {
            ExecutionMode.LIVE: executor,
            ExecutionMode.DRY_RUN: dry_run_executor or executor,
        }
        self._runner = StepRunner(self._sessions, executors, policy, limits)
        self._busy: set[str] = set()
        self._proposer = proposer

    async def create(
        self,
        runbook: Runbook,
        *,
        mode: ExecutionMode,
        started_by: str,
        runbook_label: str,
        inferred: Iterable[tuple[int, Iterable[int]]] = (),
        analysis: AnalysisRef | None = None,
    ) -> Execution:
        self._require_enabled()
        if mode is ExecutionMode.LIVE and not self._limits.allow_live:
            raise ExecutionDisabledError("live execution is not allowed (EXECUTION_ALLOW_LIVE)")
        catalog = index_catalog(await self._executor.list_tools())
        proposals = await propose_missing(
            self._proposer, runbook.steps, policy=self._policy, catalog=catalog
        )
        execution, events = plan_execution(
            runbook,
            policy=self._policy,
            catalog=catalog,
            execution_id=self._id_factory(),
            mode=mode,
            started_by=require_text(started_by, "startedBy")[:100],
            runbook_label=runbook_label,
            now=self._clock(),
            inferred=inferred,
            proposals=proposals,
            analysis=analysis,
        )
        await self._store.create(execution, events)
        return execution

    async def get(self, execution_id: str) -> Execution:
        self._require_enabled()
        return await self._store.get(execution_id)

    async def list_all(self) -> list[Execution]:
        self._require_enabled()
        return await self._store.list_all()

    async def audit(self, execution_id: str) -> tuple[list[AuditEvent], ChainVerification]:
        self._require_enabled()
        events = await self._store.audit(execution_id)
        return events, verify_chain(execution_id, events)

    async def start(self, execution_id: str, actor: str) -> Execution:
        self._require_enabled()
        active = [e for e in await self._store.list_all() if e.state in _ACTIVE]
        if len([e for e in active if e.id != execution_id]) >= self._limits.max_active:
            raise CapacityError("too many active executions (EXECUTION_MAX_ACTIVE)")
        return await self._lifecycle(execution_id, ExecutionEvent.START, actor)

    async def pause(self, execution_id: str, actor: str, reason: str) -> Execution:
        return await self._lifecycle(execution_id, ExecutionEvent.PAUSE, actor, reason)

    async def resume(self, execution_id: str, actor: str) -> Execution:
        return await self._lifecycle(execution_id, ExecutionEvent.RESUME, actor)

    async def close(self, execution_id: str, actor: str, reason: str) -> Execution:
        return await self._lifecycle(execution_id, ExecutionEvent.CLOSE, actor, reason)

    async def abort(self, execution_id: str, actor: str, reason: str) -> Execution:
        """Kill switch. Calls already sent cannot be recalled: their steps become UNKNOWN."""
        self._require_enabled()
        actor, reason = require_text(actor, "actor"), require_text(reason, "reason")
        async with self._sessions.open(execution_id) as journal:
            journal.move_execution(ExecutionEvent.ABORT, actor, reason)
            interrupt_in_flight(journal, actor, "execution aborted")
            return journal.execution

    async def decide(self, execution_id: str, step_number: int, decision: Decision) -> Execution:
        self._require_enabled()
        catalog = index_catalog(await self._executor.list_tools())
        async with self._sessions.open(execution_id) as journal:
            self._require_open(journal.execution)
            run = journal.execution.step(step_number)
            apply_decision(journal, run, decision, policy=self._policy, catalog=catalog)
            return journal.execution

    async def advance(self, execution_id: str) -> Execution:
        """Runs every call that is ready, stopping at the first one needing a person."""
        self._require_enabled()
        if execution_id not in self._busy:
            self._busy.add(execution_id)
            try:
                catalog = index_catalog(await self._executor.list_tools())
                await self._runner.run_until_blocked(execution_id, catalog)
            finally:
                self._busy.discard(execution_id)
        return await self._store.get(execution_id)

    async def rollback(self, execution_id: str, step_number: int, actor: str) -> Execution:
        """Runs a failed step's approved rollback call; success moves it to ROLLED_BACK."""
        self._require_enabled()
        actor = require_text(actor, "actor")
        if execution_id in self._busy:
            raise ConflictError("a tool call is already in progress for this execution")
        self._busy.add(execution_id)
        try:
            await run_rollback(
                self._sessions,
                self._runner,
                policy=self._policy,
                catalog=index_catalog(await self._executor.list_tools()),
                max_tool_calls=self._limits.max_tool_calls,
                execution_id=execution_id,
                step_number=step_number,
                actor=actor,
            )
        finally:
            self._busy.discard(execution_id)
        return await self.advance(execution_id)

    async def _lifecycle(
        self, execution_id: str, event: ExecutionEvent, actor: str, reason: str | None = None
    ) -> Execution:
        self._require_enabled()
        actor = require_text(actor, "actor")
        if reason is not None:
            reason = require_text(reason, "reason")
        async with self._sessions.open(execution_id) as journal:
            journal.move_execution(event, actor, reason)
            if event in (ExecutionEvent.START, ExecutionEvent.RESUME):
                journal.restart_waiting_clocks()
            return journal.execution

    def _require_enabled(self) -> None:
        if not self._limits.enabled:
            raise ExecutionDisabledError("runbook execution is disabled (EXECUTION_ENABLED)")

    @staticmethod
    def _require_open(execution: Execution) -> None:
        if execution.state in TERMINAL_EXECUTION_STATES:
            raise InvalidTransitionError(f"execution is {execution.state.value}")
