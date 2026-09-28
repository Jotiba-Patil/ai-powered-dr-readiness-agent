"""Shared helpers for the scheduler tests: a fake clock, analyze stub and a wired scheduler."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from history_support import MOCK, golden_report, make_record

from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.notify.directory import StaticContactDirectory
from dr_agent.notify.recipients import RecipientPolicy
from dr_agent.notify.senders import LogNotifier, Notifier
from dr_agent.scheduling.emailing import EmailSettings, RunEmailer
from dr_agent.scheduling.models import DailyCadence, HourlyCadence, ScheduleRun, ScheduleSpec
from dr_agent.scheduling.runner import AnalysisOutcome, Scheduler
from dr_agent.scheduling.service import Limits, ScheduleService
from dr_agent.scheduling.source import AllowedDirSource, LoadedInput
from dr_agent.scheduling.sqlite_store import SqliteScheduleStore
from dr_agent.utils.errors import AppError

# Sunday 27 Sep 2026, 05:00 UTC: an hourly :15 slot is 05:15, a daily 06:00 slot 06:00.
T0 = datetime(2026, 9, 27, 5, 0, tzinfo=UTC)
RUNBOOK = "runbooks/estimate-service.md"
INVENTORY = "inventories/healthy.json"
CONTACTS = {"Alice Chen": "alice.chen@example.com", "Bob Nguyen": "bob@other.org"}


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> datetime:
        self.now += timedelta(**delta)
        return self.now


def ids(prefix: str) -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter)}"


def hourly(minute: int = 15, **extra: object) -> ScheduleSpec:
    return ScheduleSpec.model_validate(
        {
            "name": "Estimate hourly",
            "runbook_path": RUNBOOK,
            "inventory_path": INVENTORY,
            "cadence": HourlyCadence(minute=minute),
            **extra,
        }
    )


def daily(time: str = "06:00", **extra: object) -> ScheduleSpec:
    return ScheduleSpec.model_validate(
        {"name": "Estimate daily", "runbook_path": RUNBOOK, "cadence": DailyCadence(time=time)}
        | extra
    )


@dataclass
class AnalyzeStub:
    """Stands in for `JobStore`: returns the golden report and stores it like the history."""

    db_path: Path
    store_it: bool = True
    error: AppError | None = None
    gate: asyncio.Event | None = None
    calls: list[LoadedInput] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    _ids: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    async def __call__(self, loaded: LoadedInput) -> AnalysisOutcome:
        job_id = f"job{next(self._ids)}"
        self.calls.append(loaded)
        try:
            if self.gate is not None:
                await self.gate.wait()
        except asyncio.CancelledError:
            self.cancelled.append(job_id)
            raise
        if self.error is not None:
            return AnalysisOutcome(job_id, None, False, self.error.code, self.error.message)
        if self.store_it:
            analyses = await SqliteAnalysisStore.open(self.db_path)
            await analyses.save(make_record(job_id))
        return AnalysisOutcome(job_id, golden_report(), self.store_it)


@dataclass
class Rig:
    clock: FakeClock
    store: SqliteScheduleStore
    scheduler: Scheduler
    service: ScheduleService
    analyze: AnalyzeStub
    notifier: LogNotifier


async def make_rig(
    db_path: Path,
    *,
    default_email: str | None = "dr-team@example.com",
    ui_base_url: str | None = "http://localhost:8080",
    limits: Limits | None = None,
    base_dir: Path = MOCK,
    notifier: Notifier | None = None,
) -> Rig:
    clock = FakeClock()
    store = await SqliteScheduleStore.open(db_path)
    analyze = AnalyzeStub(db_path)
    log = LogNotifier()
    emailer = RunEmailer(
        notifier or log,
        StaticContactDirectory(CONTACTS),
        EmailSettings(
            sender="dr-agent@example.com",
            policy=RecipientPolicy(frozenset({"example.com"}), default_email),
            ui_base_url=ui_base_url,
        ),
    )
    source = AllowedDirSource(base_dir)
    new_run = ids("r")
    scheduler = Scheduler(
        store,
        source=source,
        analyze=analyze,
        emailer=emailer,
        clock=clock,
        new_id=new_run,
    )
    service = ScheduleService(
        scheduler,
        source=source,
        clock=clock,
        new_id=ids("s"),
        limits=limits,
    )
    return Rig(clock, store, scheduler, service, analyze, log)


async def due_run(rig: Rig) -> ScheduleRun:
    """Create an hourly schedule, move past its first slot and let the run finish."""
    await rig.service.create(hourly(), created_by="Alice")
    rig.clock.advance(minutes=16)
    [run] = await rig.scheduler.tick()
    await rig.scheduler.wait_idle()
    return await rig.store.get_run(run.id)


async def started_run(rig: Rig) -> ScheduleRun:
    """A manual run held inside the analysis (`gate`), for cancel and shutdown tests."""
    rig.analyze.gate = asyncio.Event()
    await rig.service.create(hourly(), created_by="Alice")
    run = await rig.service.run_now("s1")
    while not rig.analyze.calls:
        await asyncio.sleep(0)
    return run


def body(message: EmailMessage) -> str:
    plain = message.get_body(("plain",))
    assert plain is not None
    return plain.get_content()
