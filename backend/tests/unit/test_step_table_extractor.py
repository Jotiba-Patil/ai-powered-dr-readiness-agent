from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.sections import parse_tree, split_sections
from dr_agent.core.step_extractor import extract_steps


def _step_nodes(markdown: str) -> list[SyntaxTreeNode]:
    sections = split_sections(parse_tree(markdown))
    return sections.sections.get("recovery steps", [])


def test_extract_steps_from_table() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "| Step | Action | Owner | Target | Estimated Minutes | Validation |\n"
        "|------|--------|-------|--------|--------------------|------------|\n"
        "| 1 | Restart | Robin | my-compute | 20 | curl -f /health |\n"
        "| 2 | Reconnect | | | 15 | |\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].action == "Restart"
    assert steps[0].owner == "Robin"
    assert steps[0].target_system == "my-compute"
    assert steps[0].estimated_minutes == 20
    assert steps[0].validation_command == "curl -f /health"
    assert steps[1].owner == "Unspecified"
    assert steps[1].target_system is None
    assert any("no owner found" in w for w in warnings)


def test_extract_steps_from_table_missing_time_defaults() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "| Action | Owner |\n"
        "|--------|-------|\n"
        "| Restart | Robin |\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].estimated_minutes == 10
    assert any("no time estimate found" in w for w in warnings)


def test_extract_steps_from_table_minutes_cell_with_units_text() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "| Action | Owner | Estimated Minutes |\n"
        "|--------|-------|--------------------|\n"
        "| Restart | Robin | 1h 30m |\n"
    )
    steps, _warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].estimated_minutes == 90


def test_extract_steps_from_table_skips_invalid_row() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "| Action | Owner | Estimated Minutes |\n"
        "|--------|-------|--------------------|\n"
        "| Bad | A | 0 |\n"
        "| Good | B | 5 |\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert len(steps) == 1
    assert steps[0].action == "Good"
    assert any("skipped" in w for w in warnings)
