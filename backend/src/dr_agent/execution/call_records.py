"""Recording a tool call's start and outcome on the step and in the audit log."""

from __future__ import annotations

from dataclasses import dataclass

from dr_agent.execution.journal import SYSTEM_ACTOR, AuditType, Journal
from dr_agent.execution.models import CallKind, StepRun, ToolCall
from dr_agent.tools.base import ToolResult


@dataclass(frozen=True)
class Outcome:
    ok: bool
    result: ToolResult | None = None
    error: str | None = None


def begin_call(journal: Journal, run: StepRun, call: ToolCall, actor: str) -> None:
    call.started_at = journal.now
    journal.execution.tool_calls_used += 1
    journal.record(
        AuditType.TOOL_CALL,
        actor,
        {
            "step": run.step_number,
            "kind": call.kind.value,
            "server": call.server,
            "tool": call.tool,
            "callHash": call.call_hash,
            "attempt": run.attempt,
        },
    )


def finish_call(journal: Journal, run: StepRun, call: ToolCall, outcome: Outcome) -> None:
    call.result, call.error, call.finished_at = outcome.result, outcome.error, journal.now
    record_late_result(journal, run.step_number, call.kind, outcome, late=False)


def record_late_result(
    journal: Journal, step_number: int, kind: CallKind, outcome: Outcome, *, late: bool = True
) -> None:
    journal.record(
        AuditType.TOOL_RESULT,
        SYSTEM_ACTOR,
        {
            "step": step_number,
            "kind": kind.value,
            "ok": outcome.ok,
            "error": outcome.error,
            "simulated": bool(outcome.result and outcome.result.simulated),
            "late": late,
        },
    )
