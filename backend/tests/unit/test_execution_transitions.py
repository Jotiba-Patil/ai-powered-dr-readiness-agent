"""Transition tables, checked exhaustively against an independent copy of design section 5."""

import itertools

import pytest

from dr_agent.execution.models import ExecutionState, StepState
from dr_agent.execution.transitions import (
    ExecutionEvent,
    StepEvent,
    execution_table,
    next_execution_state,
    next_step_state,
    step_table,
)
from dr_agent.utils.errors import InvalidTransitionError

S, Ev = StepState, StepEvent
EXPECTED_STEP = {
    (S.PLANNED, Ev.CALL_READY): S.AWAITING_APPROVAL,
    (S.PLANNED, Ev.NEEDS_REVIEW): S.PROPOSED,
    (S.PLANNED, Ev.NO_CALL): S.AWAITING_MANUAL,
    (S.PROPOSED, Ev.EDIT): S.AWAITING_APPROVAL,
    (S.PROPOSED, Ev.CONVERT_MANUAL): S.AWAITING_MANUAL,
    (S.AWAITING_APPROVAL, Ev.APPROVALS_COMPLETE): S.APPROVED,
    (S.AWAITING_APPROVAL, Ev.EDIT): S.AWAITING_APPROVAL,
    (S.AWAITING_APPROVAL, Ev.REJECT): S.REJECTED,
    (S.APPROVED, Ev.EDIT): S.AWAITING_APPROVAL,
    (S.REJECTED, Ev.EDIT): S.AWAITING_APPROVAL,
    (S.REJECTED, Ev.CONVERT_MANUAL): S.AWAITING_MANUAL,
    (S.APPROVED, Ev.START): S.RUNNING,
    (S.RUNNING, Ev.CALL_SUCCEEDED): S.VERIFYING,
    (S.RUNNING, Ev.CALL_FAILED): S.FAILED,
    (S.RUNNING, Ev.INTERRUPTED): S.UNKNOWN,
    (S.VERIFYING, Ev.VERIFY_PASSED): S.SUCCEEDED,
    (S.VERIFYING, Ev.VERIFY_FAILED): S.FAILED,
    (S.VERIFYING, Ev.INTERRUPTED): S.UNKNOWN,
    (S.UNKNOWN, Ev.VERIFY_PASSED): S.SUCCEEDED,
    (S.UNKNOWN, Ev.VERIFY_FAILED): S.FAILED,
    (S.FAILED, Ev.ROLLED_BACK): S.ROLLED_BACK,
    (S.FAILED, Ev.RETRY): S.AWAITING_APPROVAL,
    (S.AWAITING_MANUAL, Ev.MANUAL_DONE): S.MANUAL_DONE,
}
SKIPPABLE = [
    S.PLANNED,
    S.PROPOSED,
    S.AWAITING_APPROVAL,
    S.APPROVED,
    S.REJECTED,
    S.RUNNING,
    S.VERIFYING,
    S.FAILED,
    S.UNKNOWN,
    S.AWAITING_MANUAL,
]
EXPECTED_STEP |= {(state, Ev.SKIP): S.SKIPPED for state in SKIPPABLE}

X, XEv = ExecutionState, ExecutionEvent
EXPECTED_EXECUTION = {
    (X.CREATED, XEv.START): X.RUNNING,
    (X.RUNNING, XEv.PAUSE): X.PAUSED,
    (X.PAUSED, XEv.RESUME): X.RUNNING,
    (X.RUNNING, XEv.COMPLETE): X.COMPLETED,
    (X.RUNNING, XEv.CLOSE): X.FAILED,
    (X.PAUSED, XEv.CLOSE): X.FAILED,
    (X.CREATED, XEv.ABORT): X.ABORTED,
    (X.RUNNING, XEv.ABORT): X.ABORTED,
    (X.PAUSED, XEv.ABORT): X.ABORTED,
}


def test_step_table_matches_the_design() -> None:
    assert step_table() == EXPECTED_STEP


def test_execution_table_matches_the_design() -> None:
    assert execution_table() == EXPECTED_EXECUTION


@pytest.mark.parametrize(("pair", "target"), sorted(EXPECTED_STEP.items()))
def test_every_allowed_step_transition(
    pair: tuple[StepState, StepEvent], target: StepState
) -> None:
    assert next_step_state(*pair) is target


@pytest.mark.parametrize(
    "pair", [p for p in itertools.product(StepState, StepEvent) if p not in EXPECTED_STEP]
)
def test_every_other_step_transition_is_rejected(pair: tuple[StepState, StepEvent]) -> None:
    with pytest.raises(InvalidTransitionError) as info:
        next_step_state(*pair)
    assert info.value.code == "INVALID_TRANSITION"
    assert info.value.details == {"state": pair[0].value, "event": pair[1].value}


@pytest.mark.parametrize("pair", list(itertools.product(ExecutionState, ExecutionEvent)))
def test_every_execution_transition(pair: tuple[ExecutionState, ExecutionEvent]) -> None:
    if pair in EXPECTED_EXECUTION:
        assert next_execution_state(*pair) is EXPECTED_EXECUTION[pair]
    else:
        with pytest.raises(InvalidTransitionError, match="execution cannot"):
            next_execution_state(*pair)


def test_terminal_steps_cannot_even_be_skipped() -> None:
    for state in (S.SUCCEEDED, S.MANUAL_DONE, S.SKIPPED, S.ROLLED_BACK):
        with pytest.raises(InvalidTransitionError):
            next_step_state(state, Ev.SKIP)
