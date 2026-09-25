"""History-based gaps (`GapType.HISTORICAL`), deterministic like `core/gap_rules.py`.

Each rule needs a minimum sample before it says anything (design 9.2), so one
unlucky drill does not become a finding. They feed the rule-based risk score
exactly like the other rule-owned gaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from dr_agent.models.insights import ServiceHistory, StepHistory
from dr_agent.models.report import Gap, GapType, Severity


@dataclass(frozen=True)
class Thresholds:
    min_runs: int = 2  # live runs of a step (or of the service) before timing/failure rules
    min_analyses: int = 3  # analyses before dependency-trend rules
    overrun_ratio: float = 1.5  # measured median above estimate x this
    failure_share: float = 0.5  # failed or rolled back in at least this share of runs
    unhealthy_share: float = 0.5  # dependency not UP in at least this share of analyses


DEFAULT_THRESHOLDS = Thresholds()


def compute_history_gaps(
    history: ServiceHistory, limits: Thresholds = DEFAULT_THRESHOLDS
) -> list[Gap]:
    gaps: list[Gap] = []
    for step in history.steps:
        gaps.extend(_step_gaps(step, limits))
    gaps.extend(_rto_gap(history, limits))
    gaps.extend(_dependency_gaps(history, limits))
    return gaps


def _step_gaps(step: StepHistory, limits: Thresholds) -> list[Gap]:
    if step.live_runs < limits.min_runs:
        return []
    gaps: list[Gap] = []
    bad = step.failed + step.rolled_back
    if bad / step.live_runs >= limits.failure_share:
        gaps.append(
            Gap(
                type=GapType.HISTORICAL,
                description=f"Step {step.step_number} failed or was rolled back in {bad} of "
                f"{step.live_runs} past live runs.",
                severity=Severity.HIGH,
                recommendation=f"Fix the cause of step {step.step_number}'s failures and "
                "rehearse it before relying on it in a real recovery.",
            )
        )
    measured = step.median_active_minutes
    if measured is not None and measured > step.estimated_minutes * limits.overrun_ratio:
        gaps.append(
            Gap(
                type=GapType.HISTORICAL,
                description=f"Step {step.step_number} took a median of {measured:g} min in "
                f"{step.live_runs} live runs against an estimate of "
                f"{step.estimated_minutes:g} min.",
                severity=Severity.MEDIUM,
                recommendation=f"Update step {step.step_number}'s estimate to the measured time "
                "and recheck the RTO, or speed the step up.",
            )
        )
    return gaps


def _rto_gap(history: ServiceHistory, limits: Thresholds) -> list[Gap]:
    completed = [e for e in history.executions if e.state == "COMPLETED"]
    if len(completed) < limits.min_runs:
        return []
    measured = median(e.elapsed_minutes for e in completed)
    rto = completed[0].stated_rto_minutes
    if measured <= rto:
        return []
    return [
        Gap(
            type=GapType.HISTORICAL,
            description=f"Completed live runs took a median of {measured:g} min end to end, "
            f"above the stated RTO of {rto:g} min.",
            severity=Severity.HIGH,
            recommendation="Treat the RTO as not met in practice: shorten the slowest phases "
            "or agree a realistic RTO.",
        )
    ]


def _dependency_gaps(history: ServiceHistory, limits: Thresholds) -> list[Gap]:
    gaps: list[Gap] = []
    for dep in history.dependencies:
        if dep.analyses < limits.min_analyses:
            continue
        unhealthy = dep.down + dep.unreachable
        if unhealthy / dep.analyses >= limits.unhealthy_share:
            gaps.append(
                Gap(
                    type=GapType.HISTORICAL,
                    description=f"Dependency {dep.name} was down or unreachable in {unhealthy} "
                    f"of the last {dep.analyses} analyses.",
                    severity=Severity.MEDIUM,
                    recommendation=f"Make {dep.name} more reliable or add a fallback for it "
                    "to the runbook.",
                )
            )
    return gaps
