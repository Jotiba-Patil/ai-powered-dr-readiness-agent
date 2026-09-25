"""Measured timings come from audit event timestamps and state names only."""

from __future__ import annotations

from knowledge_support import event

from dr_agent.knowledge.durations import StepTiming, execution_window, step_timings
from dr_agent.knowledge.fingerprint import step_fingerprint


def test_active_and_elapsed_minutes_per_step() -> None:
    events = [
        event("e", 1, -10, "step_state", step=1, to="AWAITING_APPROVAL"),  # before the run
        event("e", 2, 0, "execution_state", to="RUNNING"),
        event("e", 3, 4, "step_state", step=1, to="RUNNING"),
        event("e", 4, 9, "step_state", step=1, to="FAILED"),
        event("e", 5, 12, "step_state", step=1, to="RUNNING"),  # retry
        event("e", 6, 15, "step_state", step=1, to="SUCCEEDED"),
        event("e", 7, 16, "step_state", step=2, to="AWAITING_MANUAL"),
        event("e", 8, 20.5, "step_state", step=2, to="MANUAL_DONE"),
        event("e", 9, 21, "execution_state", to="COMPLETED"),
    ]
    assert step_timings(events) == {
        1: StepTiming(active_minutes=11.0, elapsed_minutes=15.0),  # waits clipped to the start
        2: StepTiming(active_minutes=4.5, elapsed_minutes=4.5),
    }


def test_steps_without_an_end_or_with_odd_payloads_are_skipped() -> None:
    events = [
        event("e", 1, 0, "execution_state", to="RUNNING"),
        event("e", 2, 1, "step_state", step=1, to="RUNNING"),
        event("e", 3, 2, "step_state", step="2", to="SUCCEEDED"),
        event("e", 4, 3, "step_state", step=3, to=7),
        event("e", 5, 4, "tool_result", step=4, to="SUCCEEDED"),
        event("e", 6, 5, "step_state", step=5, to="SKIPPED"),  # never active
    ]
    assert step_timings(events) == {5: StepTiming(active_minutes=None, elapsed_minutes=None)}


def test_execution_window_needs_a_start_and_an_end() -> None:
    started = event("e", 1, 0, "execution_state", to="RUNNING")
    paused = event("e", 2, 5, "execution_state", to="PAUSED")
    done = event("e", 3, 30, "execution_state", to="COMPLETED")
    assert execution_window([started, paused]) is None
    assert execution_window([paused, done]) is None
    window = execution_window([started, paused, done])
    assert window is not None
    assert (window[1] - window[0]).total_seconds() == 30 * 60


def test_fingerprints_ignore_case_and_spacing_only() -> None:
    same = step_fingerprint("  Promote   the Replica ", "Estimate-Postgres")
    assert same == step_fingerprint("promote the replica", "estimate-postgres")
    assert same != step_fingerprint("promote the replica now", "estimate-postgres")
    assert same != step_fingerprint("promote the replica", None)
