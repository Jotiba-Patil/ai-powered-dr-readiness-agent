"""Facts built from stored analyses and finished live runs, then matched to a runbook."""

from __future__ import annotations

from exec_support import executable_runbook
from history_support import make_record
from knowledge_support import finished_run

from dr_agent.execution.models import ExecutionState, StepState
from dr_agent.knowledge.facts import PastRun, build_history, for_runbook
from dr_agent.knowledge.fingerprint import step_fingerprint
from dr_agent.models.insights import DependencyTrend
from dr_agent.models.inventory import DependencyStatus


def _runs() -> list[PastRun]:
    return [
        finished_run(
            "new",
            step_minutes={3: (0, 20), 5: (20, 25)},
            end_states={5: StepState.ROLLED_BACK},
            state=ExecutionState.FAILED,
            total=40,
            attempts={3: 2},
        ),
        finished_run("old", step_minutes={3: (0, 10), 5: (10, 12)}, total=30),
    ]


def test_steps_are_counted_and_measured_across_runs() -> None:
    history = build_history("Estimate Service", [], _runs(), dry_runs=3)
    assert (history.live_runs, history.dry_runs, history.analyses_considered) == (2, 3, 0)
    step3 = next(s for s in history.steps if s.step_number == 3)
    assert (step3.live_runs, step3.succeeded, step3.retries) == (2, 2, 1)
    assert (step3.median_active_minutes, step3.max_active_minutes) == (15.0, 20.0)
    step5 = next(s for s in history.steps if s.step_number == 5)
    assert (step5.succeeded, step5.rolled_back) == (1, 1)
    step1 = next(s for s in history.steps if s.step_number == 1)
    assert step1.median_active_minutes is None  # no timings recorded for it
    assert [(e.execution_id, e.state, e.elapsed_minutes) for e in history.executions] == [
        ("new", "FAILED", 40.0),
        ("old", "COMPLETED", 30.0),
    ]


def test_unfinished_audit_trails_give_no_outcome() -> None:
    run = finished_run("x", step_minutes={})
    run.events.pop()  # the finishing execution_state event
    assert build_history("S", [], [run], dry_runs=0).executions == []


def test_analyses_give_risk_trend_and_dependency_counts() -> None:
    healthy = make_record("a1", minutes=1, risk_score=10)
    down = make_record("a2", minutes=2, risk_score=70)
    down.report.dependency_health[0].actual_status = DependencyStatus.DOWN
    history = build_history("Estimate Service", [down, healthy], [], dry_runs=0)
    assert history.risk_scores == [10, 70]  # oldest first
    first = history.dependencies[0]
    assert first == DependencyTrend(name=first.name, analyses=2, up=1, down=1)
    assert history.empty is False
    assert build_history("S", [], [], 0).empty is True


def test_for_runbook_keeps_matching_steps_with_current_numbers() -> None:
    runbook = executable_runbook()
    history = build_history("Estimate Service", [], _runs(), dry_runs=0)
    step3 = runbook.steps[2]
    renumbered = runbook.model_copy(
        update={
            "steps": [
                step3.model_copy(
                    update={"step_number": 1, "estimated_minutes": 7, "depends_on": []}
                )
            ]
        }
    )
    matched = for_runbook(history, renumbered)
    numbers = [(s.step_number, s.estimated_minutes, s.live_runs) for s in matched.steps]
    assert numbers == [(1, 7, 2)]
    assert matched.steps[0].fingerprint == step_fingerprint(step3.action, step3.target_system)
    assert matched.executions == history.executions
