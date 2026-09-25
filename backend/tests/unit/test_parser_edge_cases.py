"""Table-driven tests over backend/tests/fixtures: empty, malformed and unusual inputs."""

from pathlib import Path

import pytest

from dr_agent.core.parser import parse_runbook
from dr_agent.utils.errors import ParseError

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_empty_runbook_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_runbook(_read("empty.md"))


def test_whitespace_only_runbook_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_runbook("   \n\n   ")


def test_no_headers_runbook_raises_parse_error_for_missing_steps() -> None:
    with pytest.raises(ParseError, match="no recovery steps"):
        parse_runbook(_read("no_headers.md"))


def test_malformed_runbook_raises_parse_error_for_duplicate_step_numbers() -> None:
    with pytest.raises(ParseError, match="failed validation"):
        parse_runbook(_read("malformed.md"))


def test_mixed_time_units_all_normalize_to_minutes() -> None:
    rb = parse_runbook(_read("mixed_time_units.md"))
    assert rb.rto_minutes == 90
    assert rb.rpo_minutes == 45
    assert [step.estimated_minutes for step in rb.steps] == [30, 120, 15, 90, 45]
    assert any("range" in w for w in rb.parser_warnings)


def test_table_sections_parse_dependencies_and_steps() -> None:
    rb = parse_runbook(_read("table_sections.md"))
    assert [d.name for d in rb.dependencies] == ["table-postgres", "table-queue"]
    assert rb.dependencies[0].critical is True
    assert rb.steps[0].estimated_minutes == 20
    assert rb.steps[0].validation_command == "curl -f localhost/health"
    assert rb.steps[1].estimated_minutes == 15


def test_bullet_steps_with_nested_validation() -> None:
    rb = parse_runbook(_read("bullet_steps.md"))
    assert len(rb.steps) == 2
    assert rb.steps[0].validation_command == "curl -f localhost/health"
    assert "select 1" in (rb.steps[1].validation_command or "")
