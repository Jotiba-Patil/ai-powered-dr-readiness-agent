from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.sections import parse_tree, split_sections
from dr_agent.core.step_extractor import extract_steps


def _step_nodes(markdown: str) -> list[SyntaxTreeNode]:
    sections = split_sections(parse_tree(markdown))
    return sections.sections.get("recovery steps", [])


def test_extract_steps_ordered_list_with_owner_time_validation() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "1. Restart the service. Owner: Alice. Estimated time: 10 min. `curl -f /health`\n"
        "2. Verify DB (after step 1). Owner: Bob. 1h 30m.\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert warnings == []
    assert steps[0].action == "Restart the service"
    assert steps[0].owner == "Alice"
    assert steps[0].estimated_minutes == 10
    assert steps[0].validation_command == "curl -f /health"
    assert steps[1].depends_on == [1]
    assert steps[1].estimated_minutes == 90


def test_extract_steps_multi_dependency_after_clause() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "1. First. Owner: A. 5 min.\n"
        "2. Second. Owner: A. 5 min.\n"
        "3. Third (after step 1 and step 2). Owner: A. 5 min.\n"
    )
    steps, _warnings = extract_steps(_step_nodes(markdown))
    assert steps[2].depends_on == [1, 2]
    assert steps[2].action == "Third"


def test_extract_steps_owner_via_handle_and_parens() -> None:
    markdown = "# Svc\n\n## Recovery Steps\n\n1. Do it @alice. 5 min.\n2. Do it (Bob). 5 min.\n"
    steps, _warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].owner == "@alice"
    assert steps[1].owner == "Bob"


def test_extract_steps_defaults_owner_and_time_when_missing() -> None:
    steps, warnings = extract_steps(_step_nodes("# Svc\n\n## Recovery Steps\n\n1. Fix it.\n"))
    assert steps[0].owner == "Unspecified"
    assert steps[0].estimated_minutes == 10
    assert any("no owner found" in w for w in warnings)
    assert any("no time estimate found" in w for w in warnings)


def test_extract_steps_target_system() -> None:
    markdown = "# Svc\n\n## Recovery Steps\n\n1. Restart. Owner: A. Target: my-cluster. 5 min.\n"
    steps, _warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].target_system == "my-cluster"


def test_extract_steps_nested_bullet_validation_command() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "- Restart it. Owner: A. 5 min.\n"
        "  - Verify: `curl -f /health`\n"
    )
    steps, _warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].validation_command == "curl -f /health"


def test_extract_steps_nested_bullet_without_validation_hint_is_ignored() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n- Restart it. Owner: A. 5 min.\n  - Just a note: `echo hi`\n"
    )
    steps, _warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].validation_command is None


def test_extract_steps_skips_step_that_fails_validation() -> None:
    """A '0 min' estimate makes estimated_minutes fail Step's gt=0 constraint."""
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n1. Do it. Owner: A. 0 min.\n2. Do it too. Owner: B. 5 min.\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert len(steps) == 1
    assert steps[0].owner == "B"
    assert any("skipped" in w for w in warnings)


def test_extract_steps_no_steps_warns() -> None:
    steps, warnings = extract_steps([])
    assert steps == []
    assert warnings == ["no recovery steps found"]
