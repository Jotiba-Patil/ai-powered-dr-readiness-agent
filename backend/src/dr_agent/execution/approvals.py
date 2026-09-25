"""Approvals bound to the call hash, with the two-person rule (ADR 0003).

Names are not authenticated in the PoC; they are compared case-insensitively
so "alice" and "Alice" count as one person. The engine calls `is_approved()`
again right before it runs a call, so an approval never covers an edited call.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError as PydanticValidationError

from dr_agent.execution.models import Approval, RiskClass, ToolCall
from dr_agent.execution.policy import REQUIRED_APPROVALS
from dr_agent.utils.errors import PolicyViolationError, StaleCallError, ValidationError


def person(name: str) -> str:
    return " ".join(name.split()).casefold()


def add_approval(
    call: ToolCall,
    *,
    verify: ToolCall | None,
    approver: str,
    comment: str | None,
    shown_hash: str,
    started_by: str,
    now: datetime,
) -> bool:
    """Records one approval and returns whether the call now has all it needs."""
    if call.risk_class is None:
        raise PolicyViolationError("the call has not passed the execution policy")
    if shown_hash != call.call_hash:
        raise StaleCallError(
            "the call changed since it was shown; review it again",
            details={"callHash": shown_hash},
        )
    try:
        approval = Approval(
            approver=approver,
            comment=comment,
            call_hash=call.call_hash,
            verify_hash=verify.call_hash if verify else None,
            created_at=now,
        )
    except PydanticValidationError as exc:
        raise ValidationError(
            "invalid approval", details={"errors": exc.errors(include_url=False)}
        ) from exc

    who = person(approval.approver)
    if who in {person(a.approver) for a in _valid(call, verify)}:
        raise PolicyViolationError(f"{approval.approver} has already approved this call")
    if call.risk_class is RiskClass.DESTRUCTIVE and who == person(started_by):
        raise PolicyViolationError(
            "the person who started the execution cannot approve a destructive call"
        )
    call.approvals.append(approval)
    return is_approved(call, verify)


def is_approved(call: ToolCall, verify: ToolCall | None) -> bool:
    if call.risk_class is None:
        return False
    names = {person(a.approver) for a in _valid(call, verify)}
    return len(names) >= REQUIRED_APPROVALS[call.risk_class]


def approvals_needed(call: ToolCall) -> int:
    return REQUIRED_APPROVALS[call.risk_class] if call.risk_class else 0


def _valid(call: ToolCall, verify: ToolCall | None) -> list[Approval]:
    verify_hash = verify.call_hash if verify else None
    return [
        a for a in call.approvals if a.call_hash == call.call_hash and a.verify_hash == verify_hash
    ]
