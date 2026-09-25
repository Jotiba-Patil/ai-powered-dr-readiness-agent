"""Step and execution state machines (design section 5).

Every state change goes through `next_step_state()` / `next_execution_state()`,
which reject anything not listed here with `InvalidTransitionError`. The API
and CLI can therefore only ever ask for events; they cannot set a state.
"""

from __future__ import annotations

from enum import StrEnum

from dr_agent.execution.models import ExecutionState, StepState
from dr_agent.utils.errors import InvalidTransitionError


class StepEvent(StrEnum):
    CALL_READY = "call_ready"  # annotated call passed policy
    NEEDS_REVIEW = "needs_review"  # AI proposal, or an annotation that failed policy
    NO_CALL = "no_call"
    EDIT = "edit"  # a named reviewer accepts or edits the call; approvals are cleared
    CONVERT_MANUAL = "convert_manual"
    APPROVALS_COMPLETE = "approvals_complete"
    REJECT = "reject"
    START = "start"
    CALL_SUCCEEDED = "call_succeeded"
    CALL_FAILED = "call_failed"
    INTERRUPTED = "interrupted"  # restart or abort while a call was in flight
    VERIFY_PASSED = "verify_passed"  # verify tool passed, or a human confirmed
    VERIFY_FAILED = "verify_failed"
    ROLLED_BACK = "rolled_back"
    RETRY = "retry"
    MANUAL_DONE = "manual_done"
    SKIP = "skip"


class ExecutionEvent(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    COMPLETE = "complete"
    CLOSE = "close"
    ABORT = "abort"


S = StepState
TERMINAL_STEP_STATES = frozenset({S.SUCCEEDED, S.MANUAL_DONE, S.SKIPPED, S.ROLLED_BACK})
# States that let a dependent step start.
SATISFIED_STEP_STATES = frozenset({S.SUCCEEDED, S.MANUAL_DONE, S.SKIPPED})
# States in which a step waits for a person while the execution keeps running.
WAITING_STEP_STATES = frozenset({S.PROPOSED, S.AWAITING_APPROVAL, S.REJECTED, S.AWAITING_MANUAL})

_STEP_TABLE: dict[tuple[StepState, StepEvent], StepState] = {
    (S.PLANNED, StepEvent.CALL_READY): S.AWAITING_APPROVAL,
    (S.PLANNED, StepEvent.NEEDS_REVIEW): S.PROPOSED,
    (S.PLANNED, StepEvent.NO_CALL): S.AWAITING_MANUAL,
    (S.PROPOSED, StepEvent.EDIT): S.AWAITING_APPROVAL,
    (S.PROPOSED, StepEvent.CONVERT_MANUAL): S.AWAITING_MANUAL,
    (S.AWAITING_APPROVAL, StepEvent.APPROVALS_COMPLETE): S.APPROVED,
    (S.AWAITING_APPROVAL, StepEvent.EDIT): S.AWAITING_APPROVAL,
    (S.AWAITING_APPROVAL, StepEvent.REJECT): S.REJECTED,
    (S.APPROVED, StepEvent.EDIT): S.AWAITING_APPROVAL,
    (S.REJECTED, StepEvent.EDIT): S.AWAITING_APPROVAL,
    (S.REJECTED, StepEvent.CONVERT_MANUAL): S.AWAITING_MANUAL,
    (S.APPROVED, StepEvent.START): S.RUNNING,
    (S.RUNNING, StepEvent.CALL_SUCCEEDED): S.VERIFYING,
    (S.RUNNING, StepEvent.CALL_FAILED): S.FAILED,
    (S.RUNNING, StepEvent.INTERRUPTED): S.UNKNOWN,
    (S.VERIFYING, StepEvent.VERIFY_PASSED): S.SUCCEEDED,
    (S.VERIFYING, StepEvent.VERIFY_FAILED): S.FAILED,
    (S.VERIFYING, StepEvent.INTERRUPTED): S.UNKNOWN,
    (S.UNKNOWN, StepEvent.VERIFY_PASSED): S.SUCCEEDED,
    (S.UNKNOWN, StepEvent.VERIFY_FAILED): S.FAILED,
    (S.FAILED, StepEvent.ROLLED_BACK): S.ROLLED_BACK,
    (S.FAILED, StepEvent.RETRY): S.AWAITING_APPROVAL,
    (S.AWAITING_MANUAL, StepEvent.MANUAL_DONE): S.MANUAL_DONE,
} | {(state, StepEvent.SKIP): S.SKIPPED for state in StepState if state not in TERMINAL_STEP_STATES}

E = ExecutionState
TERMINAL_EXECUTION_STATES = frozenset({E.COMPLETED, E.FAILED, E.ABORTED})

_EXECUTION_TABLE: dict[tuple[ExecutionState, ExecutionEvent], ExecutionState] = {
    (E.CREATED, ExecutionEvent.START): E.RUNNING,
    (E.RUNNING, ExecutionEvent.PAUSE): E.PAUSED,
    (E.PAUSED, ExecutionEvent.RESUME): E.RUNNING,
    (E.RUNNING, ExecutionEvent.COMPLETE): E.COMPLETED,
    (E.RUNNING, ExecutionEvent.CLOSE): E.FAILED,
    (E.PAUSED, ExecutionEvent.CLOSE): E.FAILED,
} | {
    (state, ExecutionEvent.ABORT): E.ABORTED
    for state in ExecutionState
    if state not in TERMINAL_EXECUTION_STATES
}


def next_step_state(state: StepState, event: StepEvent) -> StepState:
    try:
        return _STEP_TABLE[(state, event)]
    except KeyError:
        raise InvalidTransitionError(
            f"step cannot '{event.value}' while {state.value}",
            details={"state": state.value, "event": event.value},
        ) from None


def next_execution_state(state: ExecutionState, event: ExecutionEvent) -> ExecutionState:
    try:
        return _EXECUTION_TABLE[(state, event)]
    except KeyError:
        raise InvalidTransitionError(
            f"execution cannot '{event.value}' while {state.value}",
            details={"state": state.value, "event": event.value},
        ) from None


def step_table() -> dict[tuple[StepState, StepEvent], StepState]:
    """A copy of the step table (for tests and documentation)."""
    return dict(_STEP_TABLE)


def execution_table() -> dict[tuple[ExecutionState, ExecutionEvent], ExecutionState]:
    return dict(_EXECUTION_TABLE)
