"""Links an execution to the readiness analysis it was created from.

The execution follows the report's execution plan: every step in phase N waits
for all steps of phase N-1, which reproduces the report's phases exactly
(including the AI-inferred order) when the planner layers the steps again.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

from dr_agent.execution.models import AnalysisRef
from dr_agent.models.report import DRReadinessReport, ExecutionPhase


def analysis_ref(job_id: str, report: DRReadinessReport) -> AnalysisRef:
    return AnalysisRef(
        job_id=job_id,
        risk_score=report.risk_score,
        risk_level=report.risk_level.value,
        ai_analysis_available=report.ai_analysis_available,
        analyzed_at=report.meta.analyzed_at,
    )


def phase_edges(plan: Iterable[ExecutionPhase]) -> list[tuple[int, list[int]]]:
    """(step, steps it waits for): each phase waits for the whole previous phase."""
    phases = sorted(plan, key=lambda phase: phase.phase)
    return [
        (step, list(previous.steps))
        for previous, current in pairwise(phases)
        for step in current.steps
    ]
