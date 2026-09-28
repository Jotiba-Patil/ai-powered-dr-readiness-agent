"""What users can do with schedules (design sections 5.5 and 6); framework-free.

Paths are checked against the allow-list when a schedule is saved. Pausing sets
`next_run_at` to None; every resume, manual or through `pause_until`, restarts
from the next slot after now, so missed slots are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from dr_agent.notify.recipients import Recipients
from dr_agent.scheduling.models import RunState, Schedule, SchedulerState, ScheduleRun, ScheduleSpec
from dr_agent.scheduling.runner import Clock, Scheduler, next_slot
from dr_agent.scheduling.source import RunbookSource
from dr_agent.scheduling.store import IdFactory
from dr_agent.utils.errors import ConflictError, ValidationError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.scheduling")
MAX_NAME = 100


@dataclass(frozen=True)
class Limits:
    max_schedules: int = 50
    max_pause_days: int = 90


class ScheduleService:
    def __init__(
        self,
        scheduler: Scheduler,
        *,
        source: RunbookSource,
        clock: Clock,
        new_id: IdFactory,
        limits: Limits | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.store = scheduler.store
        self._source = source
        self._clock = clock
        self._new_id = new_id
        self._limits = limits or Limits()

    async def create(self, spec: ScheduleSpec, *, created_by: str) -> Schedule:
        self._source.check(spec.runbook_path, spec.inventory_path)
        if len(await self.store.list_all()) >= self._limits.max_schedules:
            raise ConflictError(
                "too many schedules", details={"maxSchedules": self._limits.max_schedules}
            )
        now = self._clock()
        schedule = Schedule.model_validate(
            {
                **spec.model_dump(),
                "id": self._new_id(),
                "created_by": _person(created_by),
                "created_at": now,
                "updated_at": now,
            }
        )
        schedule = schedule.model_copy(update={"next_run_at": next_slot(schedule, now)})
        await self.store.create(schedule)
        _log.info("schedule_created", schedule_id=schedule.id)
        return schedule

    async def update(self, schedule_id: str, spec: ScheduleSpec) -> Schedule:
        self._source.check(spec.runbook_path, spec.inventory_path)
        now = self._clock()
        current = await self.store.get(schedule_id)
        changed = Schedule.model_validate(
            {**current.model_dump(), **spec.model_dump(), "updated_at": now}
        )
        if changed.enabled:
            changed = changed.model_copy(update={"next_run_at": next_slot(changed, now)})
        await self.store.update(changed)
        return changed

    async def delete(self, schedule_id: str) -> None:
        for run in await self.store.list_runs(schedule_id, limit=1):
            if run.state is RunState.RUNNING:
                await self.scheduler.cancel(run.id)
        await self.store.delete(schedule_id)
        _log.info("schedule_deleted", schedule_id=schedule_id)

    async def pause(self, schedule_id: str, *, by: str, until: datetime | None = None) -> Schedule:
        now = self._clock()
        self._check_until(until, now)
        paused = (await self.store.get(schedule_id)).model_copy(
            update={
                "enabled": False,
                "pause_until": until,
                "paused_by": _person(by),
                "paused_at": now,
                "next_run_at": None,
                "updated_at": now,
            }
        )
        await self.store.update(paused)
        _log.info("schedule_paused", schedule_id=schedule_id, until=until)
        return paused

    async def resume(self, schedule_id: str, *, by: str) -> Schedule:
        now = self._clock()
        current = await self.store.get(schedule_id)
        resumed = current.model_copy(
            update={
                "enabled": True,
                "pause_until": None,
                "paused_by": None,
                "paused_at": None,
                "next_run_at": next_slot(current, now),
                "updated_at": now,
            }
        )
        await self.store.update(resumed)
        _log.info("schedule_resumed", schedule_id=schedule_id, by=_person(by))
        return resumed

    async def pause_all(self, *, by: str, until: datetime | None = None) -> SchedulerState:
        now = self._clock()
        self._check_until(until, now)
        state = SchedulerState(paused=True, pause_until=until, paused_by=_person(by), paused_at=now)
        await self.store.pause_all(state)
        _log.info("scheduler_paused", until=until)
        return state

    async def resume_all(self, *, by: str) -> SchedulerState:
        await self.store.resume_all(self._clock(), next_slot)
        _log.info("scheduler_resumed", by=_person(by))
        return await self.store.get_state()

    async def run_now(self, schedule_id: str) -> ScheduleRun:
        """Allowed while the schedule is paused; `ConflictError` while a run is going."""
        return await self.scheduler.run_now(schedule_id)

    async def cancel_run(self, run_id: str) -> ScheduleRun:
        return await self.scheduler.cancel(run_id)

    async def preview_recipients(self, runbook_path: str, override: list[str] | None) -> Recipients:
        """Who would be emailed for this runbook now (reads and parses the runbook)."""
        loaded = await self._source.load(runbook_path, None)
        return await self.scheduler.emailer.recipients(override, loaded.runbook.system_owner)

    def _check_until(self, until: datetime | None, now: datetime) -> None:
        if until is None:
            return
        if until <= now:
            raise ValidationError("pause until must be in the future")
        if until > now + timedelta(days=self._limits.max_pause_days):
            raise ValidationError(
                f"pause until may be at most {self._limits.max_pause_days} days ahead",
                details={"maxPauseDays": self._limits.max_pause_days},
            )


def _person(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > MAX_NAME:
        raise ValidationError(f"a name of 1-{MAX_NAME} characters is required")
    return cleaned
