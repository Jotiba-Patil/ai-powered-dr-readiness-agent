"""Request and response models for the schedule API (design scheduled-analysis section 9)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from dr_agent.config import Settings
from dr_agent.models.base import CamelModel
from dr_agent.notify.recipients import Recipients, RecipientSource
from dr_agent.scheduling.models import Schedule, SchedulerState, ScheduleRun, ScheduleSpec
from dr_agent.scheduling.next_run import describe

Person = Annotated[str, Field(min_length=1, max_length=100, description="Name of the person")]


class CreateScheduleRequest(ScheduleSpec):
    """A new schedule. `timezone` defaults to `SCHEDULER_DEFAULT_TIMEZONE` when left out."""

    created_by: Person


class PauseRequest(CamelModel):
    by: Person
    until: datetime | None = Field(
        default=None, description="Resume automatically then; empty pauses until resumed"
    )


class ResumeRequest(CamelModel):
    by: Person


class ScheduleView(Schedule):
    description: str = Field(description="Cadence in words, e.g. 'Daily 06:00 Europe/Berlin'")
    last_run: ScheduleRun | None = None

    @classmethod
    def of(cls, schedule: Schedule, last_run: ScheduleRun | None) -> ScheduleView:
        return cls.model_validate(
            {
                **schedule.model_dump(),
                "description": describe(schedule.cadence, schedule.timezone),
                "last_run": last_run,
            }
        )


class RunPage(CamelModel):
    items: list[ScheduleRun]
    next_before: datetime | None = Field(
        default=None, description="Pass as `before` for the next page; null on the last page"
    )


class SchedulerView(SchedulerState):
    """The global pause state plus the limits a client needs; never SMTP details."""

    tick_seconds: float
    max_schedules: int
    max_pause_days: int
    default_timezone: str
    email_transport: str = Field(description="`smtp` sends mail; `log` only logs it")
    default_recipient: bool = Field(description="NOTIFY_DEFAULT_EMAIL is set")
    allowed_domains: list[str]

    @classmethod
    def of(cls, state: SchedulerState, settings: Settings) -> SchedulerView:
        return cls.model_validate(
            {
                **state.model_dump(),
                "tick_seconds": settings.scheduler_tick_seconds,
                "max_schedules": settings.scheduler_max_schedules,
                "max_pause_days": settings.scheduler_max_pause_days,
                "default_timezone": settings.scheduler_default_timezone,
                "email_transport": settings.notify_transport,
                "default_recipient": settings.notify_default_email is not None,
                "allowed_domains": sorted(settings.allowed_email_domains),
            }
        )


class RecipientPreview(CamelModel):
    addresses: list[str]
    source: RecipientSource
    owner_found: bool = Field(description="The runbook owner matched the contact directory")
    dropped: int = Field(description="Addresses refused by NOTIFY_ALLOWED_DOMAINS")

    @classmethod
    def of(cls, recipients: Recipients) -> RecipientPreview:
        return cls(
            addresses=list(recipients.addresses),
            source=recipients.source,
            owner_found=recipients.owner_found,
            dropped=recipients.dropped,
        )
