"""Extracts Dependency entries from the runbook's Dependencies section."""

from __future__ import annotations

import re

from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.patterns import infer_dependency_type
from dr_agent.core.text_lines import inline_text
from dr_agent.models.runbook import Dependency

_NAME_SPLIT_RE = re.compile(r"\s+-\s+|[(:,]")
_CRITICAL_RE = re.compile(r"\bcritical\b", re.IGNORECASE)
_TRUE_VALUES = {"yes", "true", "y", "critical"}


def extract_dependencies(nodes: list[SyntaxTreeNode]) -> tuple[list[Dependency], list[str]]:
    dependencies: list[Dependency] = []
    for node in nodes:
        if node.type == "table":
            dependencies.extend(_from_table(node))
        elif node.type in ("bullet_list", "ordered_list"):
            dependencies.extend(_from_list(node))
    warnings: list[str] = []
    if not dependencies:
        warnings.append("no dependencies found in the Dependencies section")
    return dependencies, warnings


def _make_dependency(name: str, type_text: str, critical: bool) -> Dependency:
    return Dependency(
        name=name.strip(),
        type=infer_dependency_type(type_text),
        critical=critical,
    )


def _from_list(list_node: SyntaxTreeNode) -> list[Dependency]:
    deps: list[Dependency] = []
    for item in list_node.children:
        text = next(
            (inline_text(child) for child in item.children if child.type == "paragraph"), ""
        )
        if not text.strip():
            continue
        name = _NAME_SPLIT_RE.split(text, maxsplit=1)[0].strip() or text.strip()
        deps.append(_make_dependency(name, text, bool(_CRITICAL_RE.search(text))))
    return deps


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def _from_table(table: SyntaxTreeNode) -> list[Dependency]:
    header: list[str] = []
    rows: list[list[str]] = []
    for section in table.children:
        for table_row in section.children:
            cells = [inline_text(cell).strip() for cell in table_row.children]
            if section.type == "thead":
                header = [cell.lower() for cell in cells]
            else:
                rows.append(cells)

    name_idx = header.index("name") if "name" in header else None
    type_idx = header.index("type") if "type" in header else None
    critical_idx = header.index("critical") if "critical" in header else None

    deps: list[Dependency] = []
    for row in rows:
        name = _cell(row, name_idx) or (row[0] if row else "")
        if not name.strip():
            continue
        type_text = _cell(row, type_idx) or name
        critical_text = _cell(row, critical_idx)
        deps.append(
            _make_dependency(name, type_text, critical_text.strip().lower() in _TRUE_VALUES)
        )
    return deps
