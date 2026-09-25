"""Extracts service owner, RTO and RPO from the runbook preamble."""

from __future__ import annotations

from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.patterns import OWNER_RE, RPO_RE, RTO_RE, clean_markup
from dr_agent.core.text_lines import extract_lines
from dr_agent.core.time_parser import find_minutes

_DEFAULT_RTO_MINUTES = 60
_DEFAULT_RPO_MINUTES = 60


def extract_metadata(preamble: list[SyntaxTreeNode]) -> tuple[str, int, int, list[str]]:
    """Returns (owner, rto_minutes, rpo_minutes, warnings)."""
    warnings: list[str] = []
    owner: str | None = None
    rto: int | None = None
    rpo: int | None = None

    for raw_line in extract_lines(preamble):
        line = clean_markup(raw_line).strip()
        if not line:
            continue
        if owner is None and (match := OWNER_RE.search(line)):
            owner = match.group(1).split(",")[0].strip().rstrip(".")
        if rto is None and RTO_RE.search(line):
            minutes, warn = find_minutes(line)
            if minutes is not None:
                rto = minutes
                if warn:
                    warnings.append(f"RTO: {warn}")
        if rpo is None and RPO_RE.search(line):
            minutes, warn = find_minutes(line)
            if minutes is not None:
                rpo = minutes
                if warn:
                    warnings.append(f"RPO: {warn}")

    if not owner:
        owner = "Unspecified"
        warnings.append("no system owner found; defaulting owner to 'Unspecified'")
    if rto is None:
        rto = _DEFAULT_RTO_MINUTES
        warnings.append(f"no RTO found; defaulting to {_DEFAULT_RTO_MINUTES} minutes")
    if rpo is None:
        rpo = _DEFAULT_RPO_MINUTES
        warnings.append(f"no RPO found; defaulting to {_DEFAULT_RPO_MINUTES} minutes")

    return owner, rto, rpo, warnings
