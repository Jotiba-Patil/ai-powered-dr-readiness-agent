"""Approvals: bound to the call hash (and the verify call's), two-person rule for destructive."""

from datetime import UTC, datetime

import pytest

from dr_agent.execution.approvals import add_approval, approvals_needed, is_approved
from dr_agent.execution.models import CallKind, CallSource, RiskClass, ToolCall
from dr_agent.models.runbook import PlannedToolCall
from dr_agent.utils.errors import PolicyViolationError, StaleCallError, ValidationError

NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _call(risk: RiskClass | None, tool: str = "t", kind: CallKind = CallKind.MAIN) -> ToolCall:
    call = ToolCall.from_planned(
        PlannedToolCall(server="drsim", tool=tool, arguments={"a": 1}), kind, CallSource.ANNOTATED
    )
    call.risk_class = risk
    return call


def _approve(
    call: ToolCall, approver: str, *, verify: ToolCall | None = None, shown: str | None = None
) -> bool:
    return add_approval(
        call,
        verify=verify,
        approver=approver,
        comment="looks right",
        shown_hash=shown or call.call_hash,
        started_by="Olivia",
        now=NOW,
    )


@pytest.mark.parametrize("risk", [RiskClass.READ, RiskClass.WRITE])
def test_one_approval_is_enough_for_read_and_write(risk: RiskClass) -> None:
    call = _call(risk)
    assert approvals_needed(call) == 1
    assert _approve(call, "Ann") is True
    assert call.approvals[0].comment == "looks right"


def test_destructive_needs_two_different_people() -> None:
    call = _call(RiskClass.DESTRUCTIVE)
    assert approvals_needed(call) == 2
    assert _approve(call, "Ann") is False
    with pytest.raises(PolicyViolationError, match="already approved"):
        _approve(call, "  ann ")
    assert _approve(call, "Ben") is True


def test_the_starter_cannot_approve_a_destructive_call() -> None:
    with pytest.raises(PolicyViolationError, match="started the execution"):
        _approve(_call(RiskClass.DESTRUCTIVE), "olivia")


def test_the_starter_may_approve_a_write_call() -> None:
    assert _approve(_call(RiskClass.WRITE), "Olivia") is True


def test_approval_for_an_outdated_call_is_refused() -> None:
    call = _call(RiskClass.WRITE)
    with pytest.raises(StaleCallError) as info:
        _approve(call, "Ann", shown="0" * 64)
    assert info.value.code == "STALE_CALL"
    assert call.approvals == []


def test_call_that_failed_policy_cannot_be_approved() -> None:
    assert approvals_needed(_call(None)) == 0
    with pytest.raises(PolicyViolationError, match="has not passed"):
        _approve(_call(None), "Ann")
    assert is_approved(_call(None), None) is False


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_approver_name_is_validated(name: str) -> None:
    with pytest.raises(ValidationError):
        _approve(_call(RiskClass.READ), name)


def test_approval_covers_the_verify_call_it_was_given_with() -> None:
    call = _call(RiskClass.WRITE)
    verify = _call(RiskClass.READ, tool="status", kind=CallKind.VERIFY)
    assert _approve(call, "Ann", verify=verify) is True
    assert is_approved(call, verify) is True
    other = _call(RiskClass.READ, tool="other", kind=CallKind.VERIFY)
    assert is_approved(call, other) is False
    assert is_approved(call, None) is False


def test_editing_the_call_invalidates_old_approvals() -> None:
    call = _call(RiskClass.WRITE)
    _approve(call, "Ann")
    call.call_hash = "f" * 64
    assert is_approved(call, None) is False
