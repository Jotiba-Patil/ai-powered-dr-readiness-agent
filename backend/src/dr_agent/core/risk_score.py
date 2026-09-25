"""Rule-based risk score: used as the score whenever the LLM is unavailable.

When the LLM succeeds, its own risk-score proposal is used instead (it reasons
over gaps the rules cannot see, such as vague step wording). This function is
the deterministic fallback and floor, not a blend, so it stays easy to test
and explain on its own.
"""

from __future__ import annotations

from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DependencyHealth, Gap, RtoAnalysis, Severity

_RTO_INFEASIBLE_BASE = 30
_RTO_INFEASIBLE_MAX_EXTRA = 20
_SEVERITY_POINTS = {Severity.HIGH: 15, Severity.MEDIUM: 8, Severity.LOW: 3}
_DEPENDENCY_POINTS = {
    DependencyStatus.UP: 0,
    DependencyStatus.DOWN: 10,
    DependencyStatus.UNREACHABLE: 10,
    DependencyStatus.NOT_IN_INVENTORY: 5,
}


def compute_rule_based_score(
    rto: RtoAnalysis, gaps: list[Gap], dependency_health: list[DependencyHealth]
) -> int:
    score = 0.0

    if not rto.feasible:
        overage_ratio = (
            min(1.0, -rto.buffer_minutes / rto.stated_rto_minutes)
            if rto.stated_rto_minutes
            else 1.0
        )
        score += _RTO_INFEASIBLE_BASE + _RTO_INFEASIBLE_MAX_EXTRA * overage_ratio

    score += sum(_SEVERITY_POINTS[gap.severity] for gap in gaps)
    score += sum(_DEPENDENCY_POINTS[dep.actual_status] for dep in dependency_health)

    return max(0, min(100, round(score)))
