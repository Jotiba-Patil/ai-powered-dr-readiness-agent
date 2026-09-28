"""Schedule input validation: cadence, timezone, recipients."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from scheduling_support import RUNBOOK

from dr_agent.scheduling.models import MAX_RECIPIENTS, ScheduleSpec, is_email


def spec(**extra: object) -> dict[str, object]:
    return {
        "name": "x",
        "runbookPath": RUNBOOK,
        "cadence": {"kind": "daily", "time": "06:00"},
    } | extra


def test_camel_case_input_and_defaults() -> None:
    parsed = ScheduleSpec.model_validate(
        spec(cadence={"kind": "weekly", "weekday": "mon", "time": "07:30"})
    )
    assert parsed.timezone == "UTC"
    assert parsed.recipients is None
    assert parsed.cadence.kind == "weekly"


@pytest.mark.parametrize(
    "cadence",
    [
        {"kind": "daily", "time": "24:00"},
        {"kind": "daily", "time": "6:00"},
        {"kind": "hourly", "minute": 60},
        {"kind": "weekly", "weekday": "monday", "time": "06:00"},
        {"kind": "cron", "expression": "* * * * *"},
    ],
)
def test_bad_cadence_is_rejected(cadence: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScheduleSpec.model_validate(spec(cadence=cadence))


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown timezone"):
        ScheduleSpec.model_validate(spec(timezone="Mars/Olympus"))
    assert ScheduleSpec.model_validate(spec(timezone="Europe/Berlin")).timezone == "Europe/Berlin"


def test_recipients_are_checked_and_capped() -> None:
    parsed = ScheduleSpec.model_validate(spec(recipients=[" a@example.com "]))
    assert parsed.recipients == ["a@example.com"]
    assert ScheduleSpec.model_validate(spec(recipients=[])).recipients is None
    with pytest.raises(ValidationError, match="not an email address"):
        ScheduleSpec.model_validate(spec(recipients=["Alice <a@example.com>"]))
    too_many = [f"u{i}@example.com" for i in range(MAX_RECIPIENTS + 1)]
    with pytest.raises(ValidationError):
        ScheduleSpec.model_validate(spec(recipients=too_many))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ScheduleSpec.model_validate(spec(execute=True))


@pytest.mark.parametrize(
    ("address", "ok"),
    [
        ("alice.chen@example.com", True),
        ("a+tag@sub.example.co", True),
        ("no-at-sign.example.com", False),
        ("a@localhost", False),
        ("a b@example.com", False),
        ("a@example.com\r\nBcc: x@evil.org", False),
        ("a,b@example.com", False),
        ("x" * 65 + "@example.com", False),
    ],
)
def test_is_email(address: str, ok: bool) -> None:
    assert is_email(address) is ok
