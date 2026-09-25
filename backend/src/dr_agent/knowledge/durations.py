"""Measured timings from an execution's audit events (design analysis-history 9.1).

Only event types, state names and timestamps are read, never payload text.
- active: first time a step starts running (or waits for manual work) until its
  last end state, retries included;
- elapsed: from the later of "the run started" and "the step first waited for a
  person" until its last end state, so approval waits count;
- execution: first move to RUNNING until the move to a finished state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dr_agent.execution.audit import AuditEvent

_ACTIVE_START = frozenset({"RUNNING", "AWAITING_MANUAL"})
_WAIT_START = frozenset({"PROPOSED", "AWAITING_APPROVAL", "APPROVED", "AWAITING_MANUAL", "RUNNING"})
_STEP_END = frozenset({"SUCCEEDED", "FAILED", "ROLLED_BACK", "MANUAL_DONE", "SKIPPED", "UNKNOWN"})
_RUN_END = frozenset({"COMPLETED", "FAILED", "ABORTED"})


@dataclass(frozen=True)
class StepTiming:
    active_minutes: float | None
    elapsed_minutes: float | None


def _minutes(start: datetime, end: datetime) -> float:
    return round(max(0.0, (end - start).total_seconds() / 60), 1)


def _to_state(event: AuditEvent) -> str | None:
    value = event.payload.get("to")
    return value if isinstance(value, str) else None


def execution_window(events: list[AuditEvent]) -> tuple[datetime, datetime] | None:
    """(started, finished), or None when the run never started or has not finished."""
    started: datetime | None = None
    finished: datetime | None = None
    for event in events:
        if event.type != "execution_state":
            continue
        state = _to_state(event)
        if state == "RUNNING" and started is None:
            started = event.created_at
        elif state in _RUN_END:
            finished = event.created_at
    if started is None or finished is None:
        return None
    return started, finished


def step_timings(events: list[AuditEvent]) -> dict[int, StepTiming]:
    window = execution_window(events)
    run_start = window[0] if window else None
    first_active: dict[int, datetime] = {}
    first_wait: dict[int, datetime] = {}
    last_end: dict[int, datetime] = {}
    for event in events:
        step = event.payload.get("step")
        state = _to_state(event)
        if event.type != "step_state" or not isinstance(step, int) or state is None:
            continue
        if state in _ACTIVE_START:
            first_active.setdefault(step, event.created_at)
        if state in _WAIT_START:
            first_wait.setdefault(step, event.created_at)
        if state in _STEP_END:
            last_end[step] = event.created_at
    timings: dict[int, StepTiming] = {}
    for step, end in last_end.items():
        active = first_active.get(step)
        waited = first_wait.get(step)
        if waited is not None and run_start is not None:
            waited = max(waited, run_start)
        timings[step] = StepTiming(
            active_minutes=_minutes(active, end) if active else None,
            elapsed_minutes=_minutes(waited, end) if waited else None,
        )
    return timings
