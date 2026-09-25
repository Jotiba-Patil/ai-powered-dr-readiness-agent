"""Markdown DR runbook -> validated Runbook model.

Parses with markdown-it-py tokens first; regex is used only to pull fields
(owner, RTO/RPO, time estimates, validation commands) out of the resulting
plain-text lines. Missing optional fields get a default and a warning in
`parser_warnings` rather than raising. `ParseError` is raised only when the
document has no usable content or the assembled Runbook fails validation.
"""

from __future__ import annotations

from markdown_it.tree import SyntaxTreeNode
from pydantic import ValidationError as PydanticValidationError

from dr_agent.core.dependency_extractor import extract_dependencies
from dr_agent.core.metadata_extractor import extract_metadata
from dr_agent.core.sections import parse_tree, split_sections
from dr_agent.core.step_extractor import extract_steps
from dr_agent.models.runbook import Runbook
from dr_agent.utils.errors import ParseError

_DEPENDENCY_HEADINGS = {"dependencies"}
_STEP_HEADINGS = {"recovery steps", "steps", "procedure"}


def parse_runbook(raw_markdown: str) -> Runbook:
    if not raw_markdown.strip():
        raise ParseError("runbook is empty", details={"reason": "no content"})

    root = parse_tree(raw_markdown)
    sections = split_sections(root)
    warnings = list(sections.warnings)

    title = sections.title
    if not title:
        title = "Unnamed Service"
        warnings.append("no H1 service name found; defaulting to 'Unnamed Service'")

    owner, rto_minutes, rpo_minutes, meta_warnings = extract_metadata(sections.preamble)
    warnings.extend(meta_warnings)

    dependencies, dep_warnings = extract_dependencies(
        _nodes_for(sections.sections, _DEPENDENCY_HEADINGS)
    )
    warnings.extend(dep_warnings)

    steps, step_warnings = extract_steps(_nodes_for(sections.sections, _STEP_HEADINGS))
    warnings.extend(step_warnings)

    if not steps:
        raise ParseError(
            "no recovery steps found in runbook",
            details={"serviceName": title, "warnings": warnings},
        )

    try:
        return Runbook(
            service_name=title,
            system_owner=owner,
            rto_minutes=float(rto_minutes),
            rpo_minutes=float(rpo_minutes),
            dependencies=dependencies,
            steps=steps,
            raw_markdown=raw_markdown,
            parser_warnings=warnings,
        )
    except PydanticValidationError as exc:
        raise ParseError(
            "parsed runbook failed validation",
            details={"errors": exc.errors(include_url=False)},
        ) from exc


def _nodes_for(
    sections: dict[str, list[SyntaxTreeNode]], headings: set[str]
) -> list[SyntaxTreeNode]:
    for heading in headings:
        if heading in sections:
            return sections[heading]
    return []
