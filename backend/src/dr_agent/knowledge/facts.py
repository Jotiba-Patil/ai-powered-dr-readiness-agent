"""Builds a `ServiceHistory` from stored analyses and finished live executions.

Everything here is counted or measured by code (ADR 0009): step outcomes come
from each step's final state, durations from audit event timestamps.
`for_runbook()` then keeps only the steps of the runbook being analyzed,
renumbered to its step numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median

from dr_agent.execution.audit import AuditEvent
from dr_agent.execution.models import Execution, StepRun, StepState
from dr_agent.history.models import AnalysisRecord
from dr_agent.knowledge.durations import execution_window, step_timings
from dr_agent.knowledge.fingerprint import step_fingerprint
from dr_agent.models.insights import (
    DependencyTrend,
    ExecutionOutcome,
    FinishedState,
    ServiceHistory,
    StepHistory,
)
from dr_agent.models.runbook import Runbook

_OUTCOME_FIELD = {
    StepState.SUCCEEDED: "succeeded",
    StepState.FAILED: "failed",
    StepState.ROLLED_BACK: "rolled_back",
    StepState.SKIPPED: "skipped",
    StepState.MANUAL_DONE: "manual_done",
    StepState.UNKNOWN: "unknown",
}
_FINISHED: dict[str, FinishedState] = {
    "COMPLETED": "COMPLETED",
    "FAILED": "FAILED",
    "ABORTED": "ABORTED",
}


@dataclass(frozen=True)
class PastRun:
    """A finished live execution, its audit events and the RTO of the analysis it followed."""

    execution: Execution
    events: list[AuditEvent]
    stated_rto_minutes: float


def build_history(
    service: str, analyses: list[AnalysisRecord], runs: list[PastRun], dry_runs: int
) -> ServiceHistory:
    """`analyses` and `runs` newest first."""
    return ServiceHistory(
        service_name=service,
        analyses_considered=len(analyses),
        live_runs=len(runs),
        dry_runs=dry_runs,
        risk_scores=[a.report.risk_score for a in reversed(analyses)],
        executions=[o for o in (_outcome(run) for run in runs) if o is not None],
        steps=_steps(runs),
        dependencies=_dependencies(analyses),
    )


def for_runbook(history: ServiceHistory, runbook: Runbook) -> ServiceHistory:
    by_print = {s.fingerprint: s for s in history.steps}
    steps = []
    for step in runbook.steps:
        past = by_print.get(step_fingerprint(step.action, step.target_system))
        if past is not None:
            steps.append(
                past.model_copy(
                    update={
                        "step_number": step.step_number,
                        "estimated_minutes": step.estimated_minutes,
                    }
                )
            )
    return history.model_copy(update={"steps": steps})


def _outcome(run: PastRun) -> ExecutionOutcome | None:
    window = execution_window(run.events)
    state = _FINISHED.get(run.execution.state.value)
    if window is None or state is None:
        return None
    started, finished = window
    return ExecutionOutcome(
        execution_id=run.execution.id,
        state=state,
        started_at=started,
        elapsed_minutes=round((finished - started).total_seconds() / 60, 1),
        stated_rto_minutes=run.stated_rto_minutes,
    )


def _steps(runs: list[PastRun]) -> list[StepHistory]:
    grouped: dict[str, list[tuple[StepRun, float | None, float | None]]] = {}
    for run in runs:  # newest first, so the first entry of each group is the latest
        timings = step_timings(run.events)
        for step in run.execution.steps:
            timing = timings.get(step.step_number)
            grouped.setdefault(step_fingerprint(step.action, step.target_system), []).append(
                (
                    step,
                    timing.active_minutes if timing else None,
                    timing.elapsed_minutes if timing else None,
                )
            )
    return [_step_history(fingerprint, entries) for fingerprint, entries in grouped.items()]


def _step_history(
    fingerprint: str, entries: list[tuple[StepRun, float | None, float | None]]
) -> StepHistory:
    latest = entries[0][0]
    outcomes = Counter(_OUTCOME_FIELD[s.state] for s, _, _ in entries if s.state in _OUTCOME_FIELD)
    active = [a for _, a, _ in entries if a is not None]
    elapsed = [e for _, _, e in entries if e is not None]
    return StepHistory(
        step_number=latest.step_number,
        fingerprint=fingerprint,
        target_system=latest.target_system,
        estimated_minutes=latest.estimated_minutes,
        live_runs=len(entries),
        retries=sum(s.attempt - 1 for s, _, _ in entries),
        median_active_minutes=round(median(active), 1) if active else None,
        max_active_minutes=max(active) if active else None,
        median_elapsed_minutes=round(median(elapsed), 1) if elapsed else None,
        succeeded=outcomes["succeeded"],
        failed=outcomes["failed"],
        rolled_back=outcomes["rolled_back"],
        skipped=outcomes["skipped"],
        manual_done=outcomes["manual_done"],
        unknown=outcomes["unknown"],
    )


def _dependencies(analyses: list[AnalysisRecord]) -> list[DependencyTrend]:
    counts: dict[str, Counter[str]] = {}
    for analysis in analyses:
        for dep in analysis.report.dependency_health:
            counts.setdefault(dep.name, Counter())[dep.actual_status.value.lower()] += 1
    return [
        DependencyTrend(
            name=name,
            analyses=sum(c.values()),
            up=c["up"],
            down=c["down"],
            unreachable=c["unreachable"],
            not_in_inventory=c["not_in_inventory"],
        )
        for name, c in sorted(counts.items())
    ]
