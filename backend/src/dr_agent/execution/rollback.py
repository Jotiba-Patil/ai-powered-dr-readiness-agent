"""Runs a failed step's rollback call once it has its own approvals.

Same shape as the step runner: check and mark started under the lock, call
the tool without the lock, apply the outcome under the lock. A result that
arrives after an abort is only recorded.
"""

from __future__ import annotations

from dr_agent.execution.approvals import is_approved
from dr_agent.execution.call_records import (
    Outcome,
    begin_call,
    finish_call,
    record_late_result,
)
from dr_agent.execution.journal import Journal
from dr_agent.execution.models import CallKind, StepState, ToolCall
from dr_agent.execution.policy import Catalog, check_call
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.execution.runner import StepRunner
from dr_agent.execution.session import Sessions
from dr_agent.execution.transitions import TERMINAL_EXECUTION_STATES, StepEvent
from dr_agent.utils.errors import ConflictError, InvalidTransitionError, PolicyViolationError


async def run_rollback(
    sessions: Sessions,
    runner: StepRunner,
    *,
    policy: ExecutionPolicy,
    catalog: Catalog,
    max_tool_calls: int,
    execution_id: str,
    step_number: int,
    actor: str,
) -> None:
    async with sessions.open(execution_id) as journal:
        sent = _begin(journal, policy, catalog, max_tool_calls, step_number, actor)
        mode = journal.execution.mode
    outcome = await runner.invoke(sent, mode)
    async with sessions.open(execution_id) as journal:
        _finish(journal, step_number, actor, outcome)


def _begin(
    journal: Journal,
    policy: ExecutionPolicy,
    catalog: Catalog,
    max_tool_calls: int,
    step_number: int,
    actor: str,
) -> ToolCall:
    execution = journal.execution
    if execution.state in TERMINAL_EXECUTION_STATES:
        raise InvalidTransitionError(f"execution is {execution.state.value}")
    run = execution.step(step_number)
    call = run.rollback
    if run.state is not StepState.FAILED or call is None:
        raise InvalidTransitionError("only a failed step with a rollback call can roll back")
    if call.started_at is not None and call.finished_at is None:
        raise ConflictError("the rollback call is already in progress")
    call.risk_class = check_call(policy, catalog, call.planned())
    if not is_approved(call, None):
        raise PolicyViolationError("the rollback call needs its approvals first")
    if execution.tool_calls_used >= max_tool_calls:
        raise PolicyViolationError("tool call limit reached (EXECUTION_MAX_TOOL_CALLS)")
    call.reset_outcome()
    begin_call(journal, run, call, actor)
    return call.model_copy(deep=True)


def _finish(journal: Journal, step_number: int, actor: str, outcome: Outcome) -> None:
    run = journal.execution.step(step_number)
    call = run.rollback
    if call is None or call.finished_at is not None:  # aborted meanwhile
        record_late_result(journal, step_number, CallKind.ROLLBACK, outcome)
        return
    finish_call(journal, run, call, outcome)
    if outcome.ok:
        journal.move_step(run, StepEvent.ROLLED_BACK, actor, "rollback succeeded")
    else:
        run.summary = f"rollback failed: {outcome.error}"
