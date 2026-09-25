"""Orchestration-level tests for parse_runbook: defaults, heading aliases, errors."""

import pytest

from dr_agent.core.parser import parse_runbook
from dr_agent.utils.errors import ParseError


def test_missing_h1_defaults_service_name_and_warns() -> None:
    rb = parse_runbook("Owner: A\n\n## Recovery Steps\n\n1. Do it. Owner: A. 5 min.\n")
    assert rb.service_name == "Unnamed Service"
    assert any("no H1 service name found" in w for w in rb.parser_warnings)


@pytest.mark.parametrize("heading", ["Recovery Steps", "Steps", "Procedure"])
def test_step_heading_aliases_are_recognized(heading: str) -> None:
    markdown = f"# Svc\n\n## {heading}\n\n1. Do it. Owner: A. 5 min.\n"
    rb = parse_runbook(markdown)
    assert len(rb.steps) == 1


def test_raw_markdown_is_preserved_unchanged() -> None:
    """CamelModel strips surrounding whitespace; content itself is untouched."""
    markdown = "# Svc\n\n## Recovery Steps\n\n1. Do it. Owner: A. 5 min.\n"
    rb = parse_runbook(markdown)
    assert rb.raw_markdown == markdown.strip()


def test_no_recovery_steps_section_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="no recovery steps"):
        parse_runbook("# Svc\n\n## Dependencies\n\n- dep-a\n")


def test_duplicate_step_numbers_raise_parse_error_with_details() -> None:
    """Explicit 'Step N:' prefixes (not list position) drive step_number, so two
    items both prefixed 'Step 1:' collide at the Runbook uniqueness check."""
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "- Step 1: First. Owner: A. 5 min.\n"
        "- Step 1: Duplicate. Owner: A. 5 min.\n"
    )
    with pytest.raises(ParseError) as exc_info:
        parse_runbook(markdown)
    assert exc_info.value.code == "PARSE_ERROR"
    assert "errors" in (exc_info.value.details or {})
