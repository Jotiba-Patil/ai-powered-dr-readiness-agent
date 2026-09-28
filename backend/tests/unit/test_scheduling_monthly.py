"""Monthly schedules: clamping to the month's last day, "last", rollover, DST, validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dr_agent.scheduling.models import MonthlyCadence, ScheduleSpec
from dr_agent.scheduling.next_run import describe, next_run_after


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("day", "after", "expected"),
    [
        (15, utc(2026, 9, 27), utc(2026, 10, 15, 6)),  # this month's slot has passed
        (15, utc(2026, 9, 10), utc(2026, 9, 15, 6)),  # later this month
        (15, utc(2026, 9, 15, 6), utc(2026, 10, 15, 6)),  # strictly after an exact slot
        (31, utc(2026, 4, 1), utc(2026, 4, 30, 6)),  # 30-day month: its last day
        (31, utc(2026, 4, 30, 7), utc(2026, 5, 31, 6)),  # back to the 31st
        (30, utc(2026, 2, 1), utc(2026, 2, 28, 6)),  # February, normal year
        (30, utc(2028, 2, 1), utc(2028, 2, 29, 6)),  # February, leap year
        ("last", utc(2026, 2, 28, 7), utc(2026, 3, 31, 6)),
        ("last", utc(2026, 12, 31, 7), utc(2027, 1, 31, 6)),  # year rollover
        (1, utc(2026, 12, 2), utc(2027, 1, 1, 6)),
    ],
)
def test_next_monthly_slot(day: int | str, after: datetime, expected: datetime) -> None:
    cadence = MonthlyCadence.model_validate({"day": day, "time": "06:00"})
    assert next_run_after(cadence, "UTC", after) == expected


def test_monthly_follows_daylight_saving() -> None:
    # 06:00 in Berlin is 05:00 UTC in winter (CET) and 04:00 UTC in summer (CEST).
    cadence = MonthlyCadence(day=1, time="06:00")
    march = next_run_after(cadence, "Europe/Berlin", utc(2026, 2, 15))
    april = next_run_after(cadence, "Europe/Berlin", march)
    assert (march, april) == (utc(2026, 3, 1, 5), utc(2026, 4, 1, 4))


def test_monthly_in_a_timezone_ahead_of_utc() -> None:
    # 00:30 on the 1st in Kolkata is 19:00 UTC on the last day of the month before.
    slot = next_run_after(MonthlyCadence(day=1, time="00:30"), "Asia/Kolkata", utc(2026, 9, 27))
    assert slot == utc(2026, 9, 30, 19, 0)


@pytest.mark.parametrize(
    ("day", "text"),
    [
        (15, "Monthly on day 15 06:00 UTC"),
        (28, "Monthly on day 28 06:00 UTC"),
        (29, "Monthly on day 29 (last day in shorter months) 06:00 UTC"),
        ("last", "Monthly on the last day 06:00 UTC"),
    ],
)
def test_describe_monthly(day: int | str, text: str) -> None:
    cadence = MonthlyCadence.model_validate({"day": day, "time": "06:00"})
    assert describe(cadence, "UTC") == text


@pytest.mark.parametrize("day", [0, 32, "first", 1.5, None])
def test_bad_monthly_days_are_refused(day: object) -> None:
    with pytest.raises(ValidationError):
        ScheduleSpec.model_validate(
            {
                "name": "x",
                "runbookPath": "runbooks/x.md",
                "cadence": {"kind": "monthly", "day": day, "time": "06:00"},
            }
        )
