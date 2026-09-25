"""Flattens parsed markdown tree nodes into plain-text lines for regex extraction."""

from __future__ import annotations

from collections.abc import Iterable

from markdown_it.tree import SyntaxTreeNode


def inline_text(node: SyntaxTreeNode) -> str:
    """Raw source text of a node's first inline child (markup markers kept intact)."""
    for child in node.children:
        if child.type == "inline":
            return child.content
    return ""


def extract_lines(nodes: Iterable[SyntaxTreeNode]) -> list[str]:
    """One "line" of text per paragraph, list item and table row under `nodes`."""
    lines: list[str] = []
    for node in nodes:
        lines.extend(_lines_for(node))
    return lines


def _lines_for(node: SyntaxTreeNode) -> list[str]:
    if node.type == "paragraph":
        return inline_text(node).split("\n")
    if node.type in ("bullet_list", "ordered_list"):
        lines: list[str] = []
        for item in node.children:
            lines.extend(extract_lines(item.children))
        return lines
    if node.type == "table":
        return _table_lines(node)
    return []


def _table_lines(table: SyntaxTreeNode) -> list[str]:
    lines: list[str] = []
    for section in table.children:
        for row in section.children:
            cells = [inline_text(cell) for cell in row.children]
            lines.append(": ".join(cells))
    return lines
