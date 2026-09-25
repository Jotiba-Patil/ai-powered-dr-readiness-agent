from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.metadata_extractor import extract_metadata
from dr_agent.core.sections import parse_tree, split_sections


def _preamble(markdown: str) -> list[SyntaxTreeNode]:
    sections = split_sections(parse_tree(markdown))
    return sections.preamble


def test_extract_metadata_from_bold_labels() -> None:
    owner, rto, rpo, warnings = extract_metadata(
        _preamble("# Svc\n\n**Owner:** Alice\n**RTO:** 60 min\n**RPO:** 15 min\n")
    )
    assert (owner, rto, rpo) == ("Alice", 60, 15)
    assert warnings == []


def test_extract_metadata_from_inline_code_labels() -> None:
    owner, rto, rpo, _warnings = extract_metadata(
        _preamble("# Svc\n\n`Owner: Bob`\n`RTO: 2 hours`\n`RPO: 30 min`\n")
    )
    assert (owner, rto, rpo) == ("Bob", 120, 30)


def test_extract_metadata_defaults_when_missing() -> None:
    owner, rto, rpo, warnings = extract_metadata(_preamble("# Svc\n\nNo metadata here.\n"))
    assert owner == "Unspecified"
    assert rto == 60
    assert rpo == 60
    assert len(warnings) == 3


def test_extract_metadata_keeps_ambiguous_owner_literally() -> None:
    owner, _rto, _rpo, _warnings = extract_metadata(_preamble("# Svc\n\nOwner: team\n"))
    assert owner == "team"


def test_extract_metadata_from_bullet_list_key_value_lines() -> None:
    owner, rto, rpo, _warnings = extract_metadata(
        _preamble("# Svc\n\n- Owner: Dana\n- RTO: 45 min\n- RPO: 10 min\n")
    )
    assert (owner, rto, rpo) == ("Dana", 45, 10)


def test_extract_metadata_warns_on_rto_and_rpo_ranges() -> None:
    _owner, rto, rpo, warnings = extract_metadata(
        _preamble("# Svc\n\nOwner: Dana\nRTO: 10-15 min\nRPO: 5-10 min\n")
    )
    assert (rto, rpo) == (15, 10)
    assert any(w.startswith("RTO: range") for w in warnings)
    assert any(w.startswith("RPO: range") for w in warnings)


def test_extract_metadata_skips_blank_and_unstructured_lines() -> None:
    """A stray '**' has no matching emphasis pair, so cleanup leaves a blank line,
    and a thematic break has no text at all; both must be skipped, not crash."""
    markdown = "# Svc\n\n**\n\n---\n\nOwner: Dana\n"
    owner, _rto, _rpo, _warnings = extract_metadata(_preamble(markdown))
    assert owner == "Dana"


def test_extract_metadata_from_key_value_table() -> None:
    markdown = (
        "# Svc\n\n| Key | Value |\n|-----|-------|\n"
        "| Owner | Dana |\n| RTO | 45 min |\n| RPO | 10 min |\n"
    )
    owner, rto, rpo, _warnings = extract_metadata(_preamble(markdown))
    assert (owner, rto, rpo) == ("Dana", 45, 10)
