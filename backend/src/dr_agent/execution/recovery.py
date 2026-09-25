"""In-flight calls whose outcome is unknown: after an abort, or after a restart.

A call that was sent may or may not have run, so its step becomes `UNKNOWN`
for a human to check; nothing is resumed or retried automatically (ADR 0004).
At startup every `RUNNING` execution is paused, since no loop drives it any more.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from dr_agent.execution.journal import SYSTEM_ACTOR, AuditType, Journal
from dr_agent.execution.models import ExecutionState, StepState, ToolCall
from dr_agent.execution.store import ExecutionStore
from dr_agent.execution.transitions import TERMINAL_EXECUTION_STATES, ExecutionEvent, StepEvent


def interrupt_in_flight(journal: Journal, actor: str, reason: str) -> list[int]:
    """Marks every started-but-unfinished call; returns the affected step numbers."""
    affected: list[int] = []
    for run in journal.execution.steps:
        if run.state is StepState.RUNNING or (
            run.state is StepState.VERIFYING and _in_flight(run.verify)
        ):
            journal.move_step(run, StepEvent.INTERRUPTED, actor, f"{reason}; outcome unknown")
            affected.append(run.step_number)
        elif _in_flight(run.rollback) and run.rollback is not None:
            run.rollback.error = f"{reason}; outcome unknown"
            run.rollback.finished_at = journal.now
            run.summary = "rollback outcome unknown; check the system"
            journal.record(
                AuditType.TOOL_RESULT,
                actor,
                {"step": run.step_number, "kind": "rollback", "ok": False, "unknown": True},
            )
            affected.append(run.step_number)
    return affected


async def recover_interrupted(store: ExecutionStore, clock: Callable[[], datetime]) -> list[str]:
    """Run once at startup, before any request is served. Returns the recovered ids."""
    recovered: list[str] = []
    for execution in await store.list_all():
        if execution.state in TERMINAL_EXECUTION_STATES:
            continue
        journal = Journal(execution, clock())
        steps = interrupt_in_flight(journal, SYSTEM_ACTOR, "the service restarted")
        if steps:
            journal.record(AuditType.RECOVERY, SYSTEM_ACTOR, {"unknownSteps": list(steps)})
        if execution.state is ExecutionState.RUNNING:
            journal.move_execution(
                ExecutionEvent.PAUSE, SYSTEM_ACTOR, "the service restarted; resume when ready"
            )
        if journal.events:
            await store.save(execution, journal.events)
            recovered.append(execution.id)
    return recovered


def _in_flight(call: ToolCall | None) -> bool:
    return call is not None and call.started_at is not None and call.finished_at is None
