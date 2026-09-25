from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.dependency_extractor import extract_dependencies
from dr_agent.core.sections import parse_tree, split_sections
from dr_agent.models.runbook import DependencyType


def _dependency_nodes(markdown: str) -> list[SyntaxTreeNode]:
    sections = split_sections(parse_tree(markdown))
    return sections.sections.get("dependencies", [])


def test_extract_dependencies_from_bullet_list() -> None:
    deps, warnings = extract_dependencies(
        _dependency_nodes(
            "# Svc\n\n## Dependencies\n\n"
            "- estimate-postgres (database, critical)\n"
            "- rates-kafka-topic (messaging)\n"
            "- unknown-thing\n"
        )
    )
    assert warnings == []
    assert [d.name for d in deps] == ["estimate-postgres", "rates-kafka-topic", "unknown-thing"]
    assert deps[0].type is DependencyType.DATABASE
    assert deps[0].critical is True
    assert deps[1].critical is False
    assert deps[2].type is DependencyType.OTHER


def test_extract_dependencies_from_table() -> None:
    markdown = (
        "# Svc\n\n## Dependencies\n\n"
        "| Name | Type | Critical |\n"
        "|------|------|----------|\n"
        "| Kafka | messaging | yes |\n"
        "| Vault | secrets | no |\n"
    )
    deps, warnings = extract_dependencies(_dependency_nodes(markdown))
    assert warnings == []
    assert [d.name for d in deps] == ["Kafka", "Vault"]
    assert deps[0].critical is True
    assert deps[1].critical is False


def test_extract_dependencies_empty_section_warns() -> None:
    deps, warnings = extract_dependencies(_dependency_nodes("# Svc\n\n## Dependencies\n\nNone.\n"))
    assert deps == []
    assert warnings == ["no dependencies found in the Dependencies section"]


def test_extract_dependencies_missing_section_warns() -> None:
    deps, warnings = extract_dependencies([])
    assert deps == []
    assert warnings == ["no dependencies found in the Dependencies section"]


def test_dependency_list_item_with_only_a_nested_list_is_skipped() -> None:
    markdown = "# Svc\n\n## Dependencies\n\n- \n  - not-a-real-dependency\n- real-dep\n"
    deps, _warnings = extract_dependencies(_dependency_nodes(markdown))
    assert [d.name for d in deps] == ["real-dep"]


def test_dependency_name_with_hyphens_is_kept_whole() -> None:
    deps, _warnings = extract_dependencies(
        _dependency_nodes("# Svc\n\n## Dependencies\n\n- payment-ledger-db (postgres)\n")
    )
    assert deps[0].name == "payment-ledger-db"
    assert deps[0].type is DependencyType.DATABASE
