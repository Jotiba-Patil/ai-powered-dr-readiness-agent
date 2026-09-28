"""Next slot of a schedule: presets, timezones, DST gaps and overlaps, boundaries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dr_agent.scheduling.models import Cadence, DailyCadence, HourlyCadence, WeeklyCadence
from dr_agent.scheduling.next_run import describe, next_run_after

BERLIN = "Europe/Berlin"
NEW_YORK = "America/New_York"


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)  # type: ignore[misc]  # year, month, day, hour, minute


@pytest.mark.parametrize(
    ("cadence", "tz", "after", "expected"),
    [
        # hourly: later this hour, the next hour, strictly after an exact slot
        (HourlyCadence(minute=15), "UTC", utc(2026, 9, 27, 5, 0), utc(2026, 9, 27, 5, 15)),
        (HourlyCadence(minute=15), "UTC", utc(2026, 9, 27, 5, 20), utc(2026, 9, 27, 6, 15)),
        (HourlyCadence(minute=15), "UTC", utc(2026, 9, 27, 5, 15), utc(2026, 9, 27, 6, 15)),
        (HourlyCadence(minute=0), "UTC", utc(2026, 12, 31, 23, 30), utc(2027, 1, 1, 0, 0)),
        # daily: today, tomorrow, in a timezone ahead of UTC
        (DailyCadence(time="06:00"), "UTC", utc(2026, 9, 27, 5, 0), utc(2026, 9, 27, 6, 0)),
        (DailyCadence(time="06:00"), "UTC", utc(2026, 9, 27, 6, 0), utc(2026, 9, 28, 6, 0)),
        (DailyCadence(time="06:00"), BERLIN, utc(2026, 9, 27, 5, 0), utc(2026, 9, 28, 4, 0)),
        (DailyCadence(time="23:30"), "UTC", utc(2026, 2, 28, 23, 45), utc(2026, 3, 1, 23, 30)),
        # weekly: later this week, next week when the slot passed today
        (
            WeeklyCadence(weekday="mon", time="06:00"),
            "UTC",
            utc(2026, 9, 27, 12, 0),
            utc(2026, 9, 28, 6, 0),
        ),
        (
            WeeklyCadence(weekday="sun", time="06:00"),
            "UTC",
            utc(2026, 9, 27, 7, 0),
            utc(2026, 10, 4, 6, 0),
        ),
        (
            WeeklyCadence(weekday="fri", time="17:00"),
            NEW_YORK,
            utc(2026, 9, 27, 0, 0),
            utc(2026, 10, 2, 21, 0),
        ),
    ],
)
def test_next_slot(cadence: Cadence, tz: str, after: datetime, expected: datetime) -> None:
    result = next_run_after(cadence, tz, after)
    assert result == expected
    assert result.tzinfo is UTC


def test_skipped_local_time_moves_to_the_first_valid_minute() -> None:
    # Berlin springs forward on 29 Mar 2026: 02:00 CET -> 03:00 CEST, so 02:30 never happens.
    slot = next_run_after(DailyCadence(time="02:30"), BERLIN, utc(2026, 3, 28, 12, 0))
    assert slot == utc(2026, 3, 29, 1, 0)  # 03:00 CEST


def test_repeated_local_time_runs_once_at_its_first_occurrence() -> None:
    # Berlin falls back on 25 Oct 2026: 02:30 happens at 00:30 UTC (CEST) and 01:30 UTC (CET).
    daily = DailyCadence(time="02:30")
    first = next_run_after(daily, BERLIN, utc(2026, 10, 24, 12, 0))
    assert first == utc(2026, 10, 25, 0, 30)
    assert next_run_after(daily, BERLIN, first) == utc(2026, 10, 26, 1, 30)
    hourly = next_run_after(HourlyCadence(minute=30), BERLIN, first)
    assert hourly == utc(2026, 10, 25, 2, 30)  # 03:30 CET: the repeated 02:30 is not run again


def test_new_york_spring_forward_gap() -> None:
    # 8 Mar 2026: 02:00 EST -> 03:00 EDT.
    slot = next_run_after(DailyCadence(time="02:15"), NEW_YORK, utc(2026, 3, 7, 12, 0))
    assert slot == utc(2026, 3, 8, 7, 0)  # 03:00 EDT


def test_after_in_another_timezone_is_handled() -> None:
    after = datetime.fromisoformat("2026-09-27T07:00:00+02:00")  # 05:00 UTC
    assert next_run_after(HourlyCadence(minute=15), "UTC", after) == utc(2026, 9, 27, 5, 15)


@pytest.mark.parametrize(
    ("cadence", "text"),
    [
        (HourlyCadence(minute=5), "Hourly at :05 UTC"),
        (DailyCadence(time="06:00"), "Daily 06:00 UTC"),
        (WeeklyCadence(weekday="mon", time="07:30"), "Weekly Mon 07:30 UTC"),
    ],
)
def test_describe(cadence: Cadence, text: str) -> None:
    assert describe(cadence, "UTC") == text
