"""Splits a parsed markdown tree into a title, a preamble and named H2 sections."""

from __future__ import annotations

from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.text_lines import inline_text

_MD = MarkdownIt("commonmark").enable("table")


@dataclass
class RunbookSections:
    title: str | None
    preamble: list[SyntaxTreeNode]
    sections: dict[str, list[SyntaxTreeNode]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def parse_tree(markdown: str) -> SyntaxTreeNode:
    return SyntaxTreeNode(_MD.parse(markdown))


def split_sections(root: SyntaxTreeNode) -> RunbookSections:
    """Groups top-level nodes by the nearest preceding H1 (title) or H2 (section)."""
    title: str | None = None
    preamble: list[SyntaxTreeNode] = []
    sections: dict[str, list[SyntaxTreeNode]] = {}
    warnings: list[str] = []
    current_key: str | None = None

    for node in root.children:
        if node.type == "heading" and node.tag == "h1":
            heading = inline_text(node).strip()
            if title is None:
                title = heading
            else:
                warnings.append(f"multiple H1 headings found; using the first ('{title}')")
            current_key = None
            continue
        if node.type == "heading" and node.tag == "h2":
            current_key = inline_text(node).strip().lower()
            sections.setdefault(current_key, [])
            continue
        if current_key is None:
            preamble.append(node)
        else:
            sections[current_key].append(node)

    return RunbookSections(title=title, preamble=preamble, sections=sections, warnings=warnings)
