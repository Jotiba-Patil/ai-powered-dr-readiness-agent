"""Human decisions on one step, applied to the in-memory execution via a `Journal`.

Every function checks its preconditions and raises before changing anything,
so a refused decision leaves no trace but the error. Tool calls themselves are
made only by the engine.
"""

from __future__ import annotations

from dr_agent.execution.approvals import add_approval, approvals_needed
from dr_agent.execution.journal import AuditType, Journal
from dr_agent.execution.models import CallKind, CallSource, StepRun, StepState, ToolCall
from dr_agent.execution.policy import Catalog
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.execution.step_calls import evaluate_step_calls
from dr_agent.execution.transitions import TERMINAL_STEP_STATES, StepEvent, next_step_state
from dr_agent.models.runbook import PlannedToolCall
from dr_agent.utils.errors import InvalidTransitionError, PolicyViolationError, ValidationError

_MAX_TEXT = 500


def require_text(value: str | None, field: str) -> str:
    text = (value or "").strip()
    if not text or len(text) > _MAX_TEXT:
        raise ValidationError(f"{field} must be 1-{_MAX_TEXT} characters", details={"field": field})
    return text


def approve(
    journal: Journal,
    run: StepRun,
    *,
    approver: str,
    call_hash: str,
    comment: str | None,
    kind: CallKind,
) -> None:
    if kind is CallKind.ROLLBACK:
        call, verify = run.rollback, None
        if run.state is not StepState.FAILED:
            raise InvalidTransitionError("a rollback can only be approved for a failed step")
    else:
        call, verify = run.call, run.verify
        if run.state is not StepState.AWAITING_APPROVAL:
            raise InvalidTransitionError(f"step {run.step_number} is not awaiting approval")
    if call is None or kind is CallKind.VERIFY:
        raise InvalidTransitionError(f"step {run.step_number} has no {kind.value} call to approve")
    complete = add_approval(
        call,
        verify=verify,
        approver=approver,
        comment=comment,
        shown_hash=call_hash,
        started_by=journal.execution.started_by,
        now=journal.now,
    )
    journal.record(
        AuditType.APPROVAL,
        approver,
        {
            "step": run.step_number,
            "kind": kind.value,
            "callHash": call.call_hash,
            "approvals": len(call.approvals),
            "needed": approvals_needed(call),
            "comment": comment,
        },
    )
    if complete and kind is CallKind.MAIN:
        journal.move_step(run, StepEvent.APPROVALS_COMPLETE, approver)


def edit_call(
    journal: Journal,
    run: StepRun,
    *,
    editor: str,
    kind: CallKind,
    call: PlannedToolCall | None,
    policy: ExecutionPolicy,
    catalog: Catalog,
) -> None:
    """Accepts (call=None on main) or replaces a call; a verify call can be removed with None.

    Editing the main or verify call clears the step's approvals (both hashes are
    bound); editing the rollback call clears only the rollback's approvals.
    """
    editor = require_text(editor, "editor")
    if kind is CallKind.ROLLBACK:
        if run.state in TERMINAL_STEP_STATES:
            raise InvalidTransitionError(f"step {run.step_number} is already finished")
    else:
        next_step_state(run.state, StepEvent.EDIT)  # raises before anything changes

    candidate = run.model_copy(deep=True)
    field = _FIELD[kind]
    if call is not None:
        setattr(candidate, field, ToolCall.from_planned(call, kind, CallSource.EDITED))
    elif kind is CallKind.VERIFY:
        candidate.verify = None
    elif kind is CallKind.ROLLBACK or candidate.call is None:
        raise ValidationError(f"a {kind.value} call is required")
    problems = evaluate_step_calls(candidate, policy, catalog)
    if problems:
        raise PolicyViolationError(problems[0], details={"problems": problems})

    run.call, run.verify, run.rollback = candidate.call, candidate.verify, candidate.rollback
    run.policy_errors = []
    changed: ToolCall | None = getattr(run, field)
    if kind is CallKind.ROLLBACK and run.rollback is not None:
        run.rollback.approvals = []
    elif run.call is not None:
        run.call.approvals = []
    journal.record(
        AuditType.CALL_SET,
        editor,
        {
            "step": run.step_number,
            "kind": kind.value,
            "call": None if changed is None else changed.model_dump(mode="json", by_alias=True),
        },
    )
    if kind is not CallKind.ROLLBACK:
        journal.move_step(run, StepEvent.EDIT, editor)


_FIELD = {CallKind.MAIN: "call", CallKind.VERIFY: "verify", CallKind.ROLLBACK: "rollback"}


def reject(journal: Journal, run: StepRun, *, actor: str, reason: str) -> None:
    actor, reason = require_text(actor, "actor"), require_text(reason, "reason")
    journal.move_step(run, StepEvent.REJECT, actor, reason)
    if run.call is not None:
        run.call.approvals = []


def retry(journal: Journal, run: StepRun, *, actor: str) -> None:
    actor = require_text(actor, "actor")
    journal.move_step(run, StepEvent.RETRY, actor, f"retry requested (attempt {run.attempt + 1})")
    run.attempt += 1
    for call in (run.call, run.verify):
        if call is not None:
            call.approvals = []
            call.reset_outcome()


def simple(journal: Journal, run: StepRun, event: StepEvent, *, actor: str, note: str) -> None:
    """Skip, convert to manual, mark done and report an outcome: a reason is always kept."""
    journal.move_step(run, event, require_text(actor, "actor"), require_text(note, "reason"))
