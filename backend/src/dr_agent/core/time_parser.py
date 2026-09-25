"""Normalizes free-text time expressions (as written in runbooks) into minutes."""

from __future__ import annotations

import re

_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|min(?:ute)?s?|m)\b",
    re.IGNORECASE,
)
_HOURS_MINUTES_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*h(?:ours?|rs?)?\s*(\d+(?:\.\d+)?)\s*m(?:in(?:ute)?s?)?\b",
    re.IGNORECASE,
)
_HOURS_RE = re.compile(r"(?:~\s*)?(\d+(?:\.\d+)?)\s*h(?:ours?|rs?)?\b", re.IGNORECASE)
_MINUTES_RE = re.compile(r"(?:~\s*)?(\d+(?:\.\d+)?)\s*m(?:in(?:ute)?s?)?\b", re.IGNORECASE)


def find_minutes(text: str) -> tuple[int | None, str | None]:
    """Finds the first time expression in `text`. Returns (minutes, warning-or-None).

    Tries, in order: a range ("10-15 min", upper bound used and warned about),
    combined hours+minutes ("1h 30m"), bare hours ("2 hours"), bare minutes ("30 min").
    """
    match = _RANGE_RE.search(text)
    if match:
        _low, high, unit = match.groups()
        minutes = _to_minutes(float(high), unit)
        return minutes, f"range '{match.group(0).strip()}' found; using the upper bound"

    match = _HOURS_MINUTES_RE.search(text)
    if match:
        hours_str, minutes_str = match.groups()
        return round(float(hours_str) * 60 + float(minutes_str)), None

    match = _HOURS_RE.search(text)
    if match:
        return _to_minutes(float(match.group(1)), "h"), None

    match = _MINUTES_RE.search(text)
    if match:
        return _to_minutes(float(match.group(1)), "m"), None

    return None, None


def _to_minutes(value: float, unit: str) -> int:
    if unit.lower().startswith("h"):
        return round(value * 60)
    return round(value)
