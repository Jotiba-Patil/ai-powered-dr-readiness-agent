"""Schedules, their runs and the global pause state (design scheduled-analysis section 4).

`ScheduleSpec` is what a user sets; `Schedule` adds what the system tracks
(pause state, next and last run). Addresses here are only format-checked; the
domain allow-list is applied when an email is sent (`notify/recipients.py`).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from dr_agent.models.base import CamelModel
from dr_agent.models.report import RiskLevel

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
MAX_RECIPIENTS = 5
EMAIL_RE = re.compile(r"^[^@\s<>,;\"'()\\]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_TIME = r"^([01]\d|2[0-3]):[0-5]\d$"

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Name = Annotated[str, Field(min_length=1, max_length=100)]
ServerPath = Annotated[str, Field(min_length=1, max_length=512)]


class HourlyCadence(CamelModel):
    kind: Literal["hourly"] = "hourly"
    minute: int = Field(ge=0, le=59)


class DailyCadence(CamelModel):
    kind: Literal["daily"] = "daily"
    time: str = Field(pattern=_TIME, description="Local time HH:MM")


class WeeklyCadence(CamelModel):
    kind: Literal["weekly"] = "weekly"
    weekday: Weekday
    time: str = Field(pattern=_TIME, description="Local time HH:MM")


class MonthlyCadence(CamelModel):
    """Day 1-31 or "last"; a day the month lacks runs on its last day (never skipped)."""

    kind: Literal["monthly"] = "monthly"
    day: Annotated[int, Field(ge=1, le=31)] | Literal["last"]
    time: str = Field(pattern=_TIME, description="Local time HH:MM")


Cadence = Annotated[
    HourlyCadence | DailyCadence | WeeklyCadence | MonthlyCadence, Field(discriminator="kind")
]


class RunState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunTrigger(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class EmailState(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScheduleSpec(CamelModel):
    """The fields a user sets when creating or editing a schedule."""

    name: Name
    runbook_path: ServerPath
    inventory_path: ServerPath | None = None
    cadence: Cadence
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    recipients: list[str] | None = Field(default=None, max_length=MAX_RECIPIENTS)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

    @field_validator("recipients")
    @classmethod
    def _addresses(cls, value: list[str] | None) -> list[str] | None:
        if not value:
            return None
        cleaned = [address.strip() for address in value]
        bad = [address for address in cleaned if not is_email(address)]
        if bad:
            raise ValueError(f"not an email address: {bad[0][:100]!r}")
        return cleaned


class Schedule(ScheduleSpec):
    id: str = Field(pattern=ID_PATTERN)
    enabled: bool = True
    pause_until: datetime | None = None
    paused_by: str | None = Field(default=None, max_length=100)
    paused_at: datetime | None = None
    created_by: Name
    created_at: datetime
    updated_at: datetime
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


class ScheduleRun(CamelModel):
    id: str = Field(pattern=ID_PATTERN)
    schedule_id: str
    slot_at: datetime
    trigger: RunTrigger
    state: RunState = RunState.RUNNING
    started_at: datetime
    finished_at: datetime | None = None
    job_id: str | None = None
    analysis_id: str | None = Field(default=None, description="Set when the analysis is stored")
    risk_score: int | None = None
    risk_level: RiskLevel | None = None
    rto_feasible: bool | None = None
    email_state: EmailState | None = None
    email_to: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = Field(default=None, max_length=300)


class SchedulerState(CamelModel):
    """The global pause switch; one row that survives restarts."""

    paused: bool = False
    pause_until: datetime | None = None
    paused_by: str | None = None
    paused_at: datetime | None = None


def is_email(address: str) -> bool:
    return len(address) <= 254 and EMAIL_RE.fullmatch(address) is not None
