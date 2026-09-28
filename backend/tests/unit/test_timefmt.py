"""The shared display format for times (the frontend's `formatDateTime` uses the same cases)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from dr_agent.utils.errors import ValidationError
from dr_agent.utils.timefmt import display_time, zone_or_none

# Same cases as frontend/src/lib/labels.test.ts ("formatDateTime").
CASES = [
    ("2026-09-28T06:00:00+00:00", "UTC", "28 Sep 2026, 06:00 UTC"),
    ("2026-09-28T06:00:00+00:00", "Asia/Kolkata", "28 Sep 2026, 11:30 UTC+05:30"),
    ("2026-09-28T06:00:00+00:00", "America/New_York", "28 Sep 2026, 02:00 UTC-04:00"),
    ("2026-01-05T23:30:00+00:00", "Europe/Berlin", "6 Jan 2026, 00:30 UTC+01:00"),
    ("2026-03-01T04:45:00+00:00", "Asia/Kathmandu", "1 Mar 2026, 10:30 UTC+05:45"),
]


@pytest.mark.parametrize(("iso", "zone", "text"), CASES)
def test_display_time(iso: str, zone: str, text: str) -> None:
    assert display_time(datetime.fromisoformat(iso), ZoneInfo(zone)) == text


def test_seconds_and_machine_local_time() -> None:
    value = datetime(2026, 9, 28, 6, 0, 5, tzinfo=UTC)
    assert display_time(value, UTC, seconds=True) == "28 Sep 2026, 06:00:05 UTC"
    local = display_time(value)  # this machine's zone: only the shape is predictable
    assert local.startswith(("27 Sep 2026", "28 Sep 2026", "29 Sep 2026"))
    assert " UTC" in local


def test_zone_or_none() -> None:
    assert zone_or_none(None) is None
    assert zone_or_none("") is None
    assert zone_or_none("Asia/Calcutta") == ZoneInfo("Asia/Calcutta")  # old names still work
    with pytest.raises(ValidationError, match="unknown timezone"):
        zone_or_none("Mars/Olympus")
    with pytest.raises(ValidationError):
        zone_or_none("../etc/passwd")
