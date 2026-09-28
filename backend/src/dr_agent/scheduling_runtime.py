"""Builds the scheduler from settings (ADR 0010): the one place, like `execution_runtime.py`.

The API lifespan calls `open_schedules()` when `SCHEDULER_ENABLED=true`, then
starts the ticker. The analyze callable is passed in, so this module does not
depend on the web layer; the API gives it `JobStore`-backed analysis.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from dr_agent.config import Settings
from dr_agent.notify.directory import ContactDirectory
from dr_agent.notify.senders import Notifier
from dr_agent.scheduling.emailing import RunEmailer
from dr_agent.scheduling.runner import Analyze, Scheduler
from dr_agent.scheduling.service import Limits, ScheduleService
from dr_agent.scheduling.source import AllowedDirSource
from dr_agent.scheduling.sqlite_store import SqliteScheduleStore
from dr_agent.utils.logging import get_logger
from dr_agent.wiring import build_directory, build_notifier, email_settings

Clock = Callable[[], datetime]

_log = get_logger("dr_agent.scheduling")


async def open_schedules(
    settings: Settings,
    analyze: Analyze,
    *,
    clock: Clock | None = None,
    notifier: Notifier | None = None,
    directory: ContactDirectory | None = None,
) -> ScheduleService:
    """The schedule service over the shared database; runs left `running` are closed first."""
    now = clock or (lambda: datetime.now(UTC))
    source = AllowedDirSource(Path(settings.api_allowed_dir))
    emailer = RunEmailer(
        notifier or build_notifier(settings),
        directory or build_directory(settings),
        email_settings(settings),
    )
    scheduler = Scheduler(
        await SqliteScheduleStore.open(settings.database_path),
        source=source,
        analyze=analyze,
        emailer=emailer,
        clock=now,
        new_id=lambda: uuid.uuid4().hex,
        tick_seconds=settings.scheduler_tick_seconds,
    )
    service = ScheduleService(
        scheduler,
        source=source,
        clock=now,
        new_id=lambda: uuid.uuid4().hex,
        limits=Limits(settings.scheduler_max_schedules, settings.scheduler_max_pause_days),
    )
    interrupted = await scheduler.recover()
    _log.info(
        "scheduler_opened",
        transport=settings.notify_transport,
        interrupted_runs=interrupted,
        default_recipient=settings.notify_default_email is not None,
    )
    return service
