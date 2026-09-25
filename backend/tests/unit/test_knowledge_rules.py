"""Each history rule at and around its threshold (design analysis-history 9.3)."""

from __future__ import annotations

from datetime import datetime

import pytest

from dr_agent.knowledge.rules import Thresholds, compute_history_gaps
from dr_agent.models.insights import DependencyTrend, ExecutionOutcome, ServiceHistory, StepHistory
from dr_agent.models.report import GapType, Severity

T = datetime(2026, 9, 25)


def _history(**parts: object) -> ServiceHistory:
    base: dict[str, object] = {
        "service_name": "S",
        "analyses_considered": 0,
        "live_runs": 0,
        "dry_runs": 0,
    }
    return ServiceHistory.model_validate(base | parts)


def _step(**fields: object) -> StepHistory:
    base: dict[str, object] = {
        "step_number": 2,
        "fingerprint": "f",
        "estimated_minutes": 10,
        "live_runs": 2,
    }
    return StepHistory.model_validate(base | fields)


def _run(state: str, minutes: float) -> ExecutionOutcome:
    return ExecutionOutcome(
        execution_id="e", state=state, started_at=T, elapsed_minutes=minutes, stated_rto_minutes=60
    )


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (_step(failed=1, succeeded=1), 1),  # 1 of 2: exactly the 50% share
        (_step(rolled_back=1, succeeded=1), 1),
        (_step(succeeded=2), 0),
        (_step(live_runs=3, failed=1, succeeded=2), 0),  # 33%
        (_step(live_runs=1, failed=1), 0),  # below the minimum sample
    ],
)
def test_failed_or_rolled_back_steps(step: StepHistory, expected: int) -> None:
    gaps = compute_history_gaps(_history(steps=[step]))
    assert len(gaps) == expected
    if gaps:
        assert (gaps[0].type, gaps[0].severity) == (GapType.HISTORICAL, Severity.HIGH)
        assert gaps[0].description.startswith("Step 2 failed or was rolled back in 1 of 2")


@pytest.mark.parametrize(("median", "expected"), [(15.0, 0), (15.1, 1), (None, 0)])
def test_slow_steps(median: float | None, expected: int) -> None:
    step = _step(succeeded=2, median_active_minutes=median)
    gaps = compute_history_gaps(_history(steps=[step]))
    assert len(gaps) == expected
    if gaps:
        assert gaps[0].severity is Severity.MEDIUM
        assert (
            "median of 15.1 min in 2 live runs against an estimate of 10 min" in gaps[0].description
        )


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([_run("COMPLETED", 70), _run("COMPLETED", 80)], 1),
        ([_run("COMPLETED", 60), _run("COMPLETED", 60)], 0),  # at the RTO is not above it
        ([_run("COMPLETED", 90), _run("FAILED", 90)], 0),  # only one completed run
    ],
)
def test_measured_rto(runs: list[ExecutionOutcome], expected: int) -> None:
    gaps = compute_history_gaps(_history(executions=runs))
    assert len(gaps) == expected
    if gaps:
        assert "median of 75 min end to end, above the stated RTO of 60 min" in gaps[0].description


@pytest.mark.parametrize(
    ("trend", "expected"),
    [
        (DependencyTrend(name="db", analyses=4, down=1, unreachable=1, up=2), 1),
        (DependencyTrend(name="db", analyses=4, down=1, up=3), 0),
        (DependencyTrend(name="db", analyses=2, down=2), 0),  # below the minimum sample
    ],
)
def test_unhealthy_dependencies(trend: DependencyTrend, expected: int) -> None:
    gaps = compute_history_gaps(_history(dependencies=[trend]))
    assert len(gaps) == expected


def test_thresholds_can_be_changed() -> None:
    step = _step(live_runs=1, failed=1)
    assert compute_history_gaps(_history(steps=[step]), Thresholds(min_runs=1))
