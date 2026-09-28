"""`ScheduleStore` protocol: schedules, runs and the global pause state (ADR 0010)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from dr_agent.scheduling.models import Schedule, SchedulerState, ScheduleRun

NextSlot = Callable[[Schedule, datetime], datetime]
IdFactory = Callable[[], str]


class ScheduleStore(Protocol):
    async def create(self, schedule: Schedule) -> None: ...

    async def get(self, schedule_id: str) -> Schedule:
        """Raises `NotFoundError` for an unknown id."""
        ...

    async def list_all(self) -> list[Schedule]:
        """Oldest first."""
        ...

    async def update(self, schedule: Schedule) -> None:
        """Replaces every field; `NotFoundError` for an unknown id."""
        ...

    async def delete(self, schedule_id: str) -> None:
        """Deletes the schedule and its runs; `NotFoundError` for an unknown id."""
        ...

    async def claim_due(
        self, now: datetime, next_slot: NextSlot, new_id: IdFactory
    ) -> list[ScheduleRun]:
        """In one transaction: apply expired pauses, then start a run for each due slot.

        A slot runs at most once; a schedule with a run still going skips the slot.
        """
        ...

    async def start_manual(self, schedule_id: str, now: datetime, run_id: str) -> ScheduleRun:
        """`ConflictError` while a run of that schedule is still going."""
        ...

    async def save_run(self, run: ScheduleRun) -> None: ...

    async def get_run(self, run_id: str) -> ScheduleRun:
        """Raises `NotFoundError` for an unknown id."""
        ...

    async def list_runs(
        self, schedule_id: str, *, limit: int, before: datetime | None = None
    ) -> list[ScheduleRun]:
        """Newest first; `before` continues a page."""
        ...

    async def latest_runs(self) -> dict[str, ScheduleRun]:
        """The newest run of every schedule that has one."""
        ...

    async def fail_interrupted(self, now: datetime) -> int:
        """Marks runs left `running` by a restart as failed; returns how many."""
        ...

    async def get_state(self) -> SchedulerState: ...

    async def pause_all(self, state: SchedulerState) -> None: ...

    async def resume_all(self, now: datetime, next_slot: NextSlot) -> None:
        """Clears the global pause; every active schedule restarts from its next slot after now."""
        ...
