from dr_agent.core.sections import parse_tree, split_sections


def test_split_sections_groups_by_heading() -> None:
    root = parse_tree(
        "# My Service\n\nIntro line.\n\n"
        "## Dependencies\n\n- dep-a\n\n"
        "## Recovery Steps\n\n1. Do it.\n"
    )
    sections = split_sections(root)

    assert sections.title == "My Service"
    assert len(sections.preamble) == 1
    assert "dependencies" in sections.sections
    assert "recovery steps" in sections.sections
    assert sections.warnings == []


def test_split_sections_warns_on_duplicate_h1() -> None:
    root = parse_tree("# First\n\n# Second\n\nBody.\n")
    sections = split_sections(root)

    assert sections.title == "First"
    assert any("multiple H1" in warning for warning in sections.warnings)


def test_split_sections_with_no_headings_is_all_preamble() -> None:
    root = parse_tree("Just a paragraph with no headings at all.\n")
    sections = split_sections(root)

    assert sections.title is None
    assert sections.sections == {}
    assert len(sections.preamble) == 1
