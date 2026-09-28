"""One way to show a time to a person (design scheduled-analysis section 18.4).

Times are stored and exchanged in UTC; people see them in their local time as
`28 Sep 2026, 11:30 UTC+05:30`. The numeric offset is used instead of zone
abbreviations because browsers and Python name zones differently. The frontend's
`formatDateTime()` produces the same text; both are tested on the same cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dr_agent.utils.errors import ValidationError

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def display_time(value: datetime, zone: tzinfo | None = None, *, seconds: bool = False) -> str:
    """`value` (aware) in `zone`, or in this machine's local time when `zone` is None."""
    local = value.astimezone(zone) if zone is not None else value.astimezone()
    clock = f"{local:%H:%M:%S}" if seconds else f"{local:%H:%M}"
    return f"{local.day} {_MONTHS[local.month - 1]} {local.year}, {clock} {offset_label(local)}"


def offset_label(local: datetime) -> str:
    """`UTC`, `UTC+05:30` or `UTC-04:00`."""
    offset = local.utcoffset() or timedelta(0)
    if not offset:
        return "UTC"
    sign = "-" if offset < timedelta(0) else "+"
    minutes = abs(int(offset.total_seconds())) // 60
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def zone_or_none(name: str | None) -> ZoneInfo | None:
    """A validated IANA zone, or None for "not given"; `ValidationError` for an unknown name."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"unknown timezone {name[:64]!r}") from exc
