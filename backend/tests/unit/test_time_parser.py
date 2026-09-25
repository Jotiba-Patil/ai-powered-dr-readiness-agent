import pytest

from dr_agent.core.time_parser import find_minutes


@pytest.mark.parametrize(
    ("text", "minutes", "has_warning"),
    [
        ("30 min", 30, False),
        ("Estimated time: 45 minutes", 45, False),
        ("2 hours", 120, False),
        ("1h 30m", 90, False),
        ("2hr 15min", 135, False),
        ("~45m", 45, False),
        ("10-15 min", 15, True),
        ("1-2 hours", 120, True),
        ("no time here", None, False),
        ("", None, False),
    ],
)
def test_find_minutes(text: str, minutes: int | None, has_warning: bool) -> None:
    result, warning = find_minutes(text)
    assert result == minutes
    assert (warning is not None) is has_warning
