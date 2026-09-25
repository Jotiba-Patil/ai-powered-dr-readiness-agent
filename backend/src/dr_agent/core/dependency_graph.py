"""Merges a runbook's explicit step dependencies with inferred ones.

Shared by the analysis (AI-inferred `stepDependencies`) and the execution
planner, so both build their phases from the same graph. Inferred edges that
name unknown steps, or a step itself, are dropped.
"""

from __future__ import annotations

from collections.abc import Iterable

from dr_agent.models.runbook import Step


def merge_depends_on(
    steps: list[Step], inferred: Iterable[tuple[int, Iterable[int]]] = ()
) -> dict[int, set[int]]:
    known = {step.step_number for step in steps}
    merged: dict[int, set[int]] = {step.step_number: set(step.depends_on) for step in steps}
    for step_number, depends_on in inferred:
        if step_number not in known:
            continue
        merged[step_number] |= {d for d in depends_on if d in known and d != step_number}
    return merged
