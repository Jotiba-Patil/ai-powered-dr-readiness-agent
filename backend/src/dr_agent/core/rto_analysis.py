"""Deterministic RTO feasibility: totals, buffer and bottleneck steps.

Bottleneck steps are only reported when the RTO is missed: the longest steps are
picked, greedily, until removing them would have closed the gap. This gives a
minimal, explainable set of "the steps causing the overage" rather than every step.
"""

from __future__ import annotations

from dr_agent.models.report import RtoAnalysis
from dr_agent.models.runbook import Runbook


def compute_rto_analysis(runbook: Runbook) -> RtoAnalysis:
    total_minutes = sum(step.estimated_minutes for step in runbook.steps)
    buffer_minutes = runbook.rto_minutes - total_minutes
    feasible = buffer_minutes >= 0

    return RtoAnalysis(
        feasible=feasible,
        total_estimated_minutes=total_minutes,
        stated_rto_minutes=runbook.rto_minutes,
        buffer_minutes=buffer_minutes,
        bottleneck_steps=[] if feasible else _bottleneck_steps(runbook, total_minutes),
    )


def _bottleneck_steps(runbook: Runbook, total_minutes: float) -> list[int]:
    overage = total_minutes - runbook.rto_minutes
    ranked = sorted(runbook.steps, key=lambda step: step.estimated_minutes, reverse=True)

    picked: list[int] = []
    removed = 0.0
    for step in ranked:
        if removed >= overage:
            break
        picked.append(step.step_number)
        removed += step.estimated_minutes
    return sorted(picked)
