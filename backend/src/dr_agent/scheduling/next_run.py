"""When a schedule runs next (design scheduled-analysis section 5.1). Pure functions.

Candidates are local wall-clock times in the schedule's timezone, tried in order;
the first one after `after` wins. DST: a wall time that does not exist (clocks
spring forward) moves to the first valid minute after it; one that occurs twice
(clocks fall back) is taken once, at its first occurrence (`fold=0`).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dr_agent.scheduling.models import (
    WEEKDAYS,
    Cadence,
    DailyCadence,
    HourlyCadence,
    MonthlyCadence,
    WeeklyCadence,
)

_MAX_GAP_MINUTES = 180  # longer than any real DST jump


def next_run_after(cadence: Cadence, timezone: str, after: datetime) -> datetime:
    """The first slot strictly after `after` (aware), as an aware UTC datetime."""
    zone = ZoneInfo(timezone)
    start = after.astimezone(zone).replace(tzinfo=None)
    for wall in _candidates(cadence, start):
        slot = _to_utc(wall, zone)
        if slot > after:
            return slot
    raise AssertionError("no slot found")  # pragma: no cover - candidates cover every preset


def describe(cadence: Cadence, timezone: str) -> str:
    """Short text for lists and emails, e.g. 'Daily 06:00 Europe/Berlin'."""
    if isinstance(cadence, HourlyCadence):
        return f"Hourly at :{cadence.minute:02d} {timezone}"
    if isinstance(cadence, DailyCadence):
        return f"Daily {cadence.time} {timezone}"
    if isinstance(cadence, MonthlyCadence):
        if cadence.day == "last":
            return f"Monthly on the last day {cadence.time} {timezone}"
        clamp = " (last day in shorter months)" if cadence.day > 28 else ""
        return f"Monthly on day {cadence.day}{clamp} {cadence.time} {timezone}"
    return f"Weekly {cadence.weekday.title()} {cadence.time} {timezone}"


def _candidates(cadence: Cadence, start: datetime) -> Iterator[datetime]:
    """Wall times from just before `start`, in order (the caller filters by UTC)."""
    if isinstance(cadence, HourlyCadence):
        hour = start.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        for step in range(0, 9 * 24):
            yield (hour + timedelta(hours=step)).replace(minute=cadence.minute)
        return
    at = _parse_time(cadence.time)
    if isinstance(cadence, MonthlyCadence):
        yield from _monthly(cadence, start, at)
        return
    for offset in range(-1, 9):
        day = start.date() + timedelta(days=offset)
        if isinstance(cadence, WeeklyCadence) and not _is_weekday(day, cadence):
            continue
        yield datetime.combine(day, at)


def _monthly(cadence: MonthlyCadence, start: datetime, at: time) -> Iterator[datetime]:
    """This month's slot and the next 14, each clamped to the month's last day."""
    year, month = start.year, start.month
    for _ in range(15):
        last = calendar.monthrange(year, month)[1]
        day = last if cadence.day == "last" else min(cadence.day, last)
        yield datetime.combine(date(year, month, day), at)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _is_weekday(day: date, cadence: WeeklyCadence) -> bool:
    return WEEKDAYS[day.weekday()] == cadence.weekday


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _to_utc(wall: datetime, zone: ZoneInfo) -> datetime:
    for minutes in range(_MAX_GAP_MINUTES + 1):
        candidate = wall + timedelta(minutes=minutes)
        if _exists(candidate, zone):
            return candidate.replace(tzinfo=zone, fold=0).astimezone(UTC)
    raise AssertionError("no valid local time")  # pragma: no cover - DST gaps are short


def _exists(wall: datetime, zone: ZoneInfo) -> bool:
    """False for a wall time skipped by a DST jump (it does not survive a round trip)."""
    aware = wall.replace(tzinfo=zone, fold=0)
    return aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == wall
