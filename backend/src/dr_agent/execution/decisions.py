"""Typed human decisions on a step and the one dispatcher that applies them.

The API and CLI build one of these from a request; `apply_decision()` routes
it to `step_actions`. Keeping decisions as data makes each request explicit
and lets every one of them be audited the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

from dr_agent.execution import step_actions
from dr_agent.execution.journal import Journal
from dr_agent.execution.models import CallKind, StepRun
from dr_agent.execution.policy import Catalog
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.execution.transitions import StepEvent
from dr_agent.models.runbook import PlannedToolCall


@dataclass(frozen=True)
class Approve:
    approver: str
    call_hash: str
    comment: str | None = None
    kind: CallKind = CallKind.MAIN


@dataclass(frozen=True)
class EditCall:
    editor: str
    call: PlannedToolCall | None = None
    kind: CallKind = CallKind.MAIN


@dataclass(frozen=True)
class Reject:
    actor: str
    reason: str


@dataclass(frozen=True)
class Skip:
    actor: str
    reason: str


@dataclass(frozen=True)
class ConvertToManual:
    actor: str
    reason: str


@dataclass(frozen=True)
class MarkDone:
    actor: str
    note: str = "done by hand"


@dataclass(frozen=True)
class ReportOutcome:
    """A human's verdict on a step that is VERIFYING (no verify tool) or UNKNOWN."""

    actor: str
    succeeded: bool
    note: str


@dataclass(frozen=True)
class Retry:
    actor: str


Decision = Approve | EditCall | Reject | Skip | ConvertToManual | MarkDone | ReportOutcome | Retry


def apply_decision(
    journal: Journal,
    run: StepRun,
    decision: Decision,
    *,
    policy: ExecutionPolicy,
    catalog: Catalog,
) -> None:
    match decision:
        case Approve(approver=approver, call_hash=call_hash, comment=comment, kind=kind):
            step_actions.approve(
                journal, run, approver=approver, call_hash=call_hash, comment=comment, kind=kind
            )
        case EditCall(editor=editor, call=call, kind=kind):
            step_actions.edit_call(
                journal, run, editor=editor, kind=kind, call=call, policy=policy, catalog=catalog
            )
        case Reject(actor=actor, reason=reason):
            step_actions.reject(journal, run, actor=actor, reason=reason)
        case Skip(actor=actor, reason=reason):
            step_actions.simple(journal, run, StepEvent.SKIP, actor=actor, note=reason)
        case ConvertToManual(actor=actor, reason=reason):
            step_actions.simple(journal, run, StepEvent.CONVERT_MANUAL, actor=actor, note=reason)
        case MarkDone(actor=actor, note=note):
            step_actions.simple(journal, run, StepEvent.MANUAL_DONE, actor=actor, note=note)
        case ReportOutcome(actor=actor, succeeded=succeeded, note=note):
            event = StepEvent.VERIFY_PASSED if succeeded else StepEvent.VERIFY_FAILED
            step_actions.simple(journal, run, event, actor=actor, note=note)
        case Retry(actor=actor):
            step_actions.retry(journal, run, actor=actor)
