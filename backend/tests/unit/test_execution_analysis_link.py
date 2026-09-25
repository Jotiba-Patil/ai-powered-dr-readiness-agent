"""An execution follows the analysis it came from: same phases, analysis recorded."""

from datetime import UTC, datetime
from pathlib import Path

from exec_support import OPERATOR, drsim_catalog, drsim_policy, executable_runbook

from dr_agent.execution.analysis_link import analysis_ref, phase_edges
from dr_agent.execution.models import ExecutionMode
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.models.report import DRReadinessReport, ExecutionPhase
from dr_agent.models.runbook import Runbook

NOW = datetime(2026, 9, 24, tzinfo=UTC)
GOLDEN = Path(__file__).resolve().parents[3] / "mock-data/expected-reports/estimate-service.json"


def _phase(number: int, steps: list[int]) -> ExecutionPhase:
    return ExecutionPhase(phase=number, steps=steps, estimated_minutes=5, gate="-")


def _phases_of(runbook: Runbook, plan: list[ExecutionPhase]) -> dict[int, int]:
    execution, _ = plan_execution(
        runbook,
        policy=drsim_policy(),
        catalog=index_catalog(drsim_catalog()),
        execution_id="exec-1",
        mode=ExecutionMode.DRY_RUN,
        started_by=OPERATOR,
        runbook_label="s.md",
        now=NOW,
        inferred=phase_edges(plan),
    )
    return {run.step_number: run.phase for run in execution.steps}


def test_each_phase_waits_for_the_whole_previous_phase() -> None:
    plan = [_phase(2, [3]), _phase(1, [1, 2]), _phase(3, [4, 5])]
    assert phase_edges(plan) == [(3, [1, 2]), (4, [3]), (5, [3])]
    assert phase_edges([_phase(1, [1])]) == []


def test_execution_reproduces_the_reports_phases() -> None:
    # The report (e.g. with AI-inferred order) put step 2 after step 1; the runbook alone does not.
    plan = [_phase(1, [1]), _phase(2, [2, 3]), _phase(3, [4]), _phase(4, [5])]
    assert _phases_of(executable_runbook(), plan) == {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}
    # Without a plan the runbook's own "after step N" order applies.
    assert _phases_of(executable_runbook(), []) == {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}


def test_analysis_ref_summarizes_the_report() -> None:
    report = DRReadinessReport.model_validate_json(GOLDEN.read_text("utf-8"))
    ref = analysis_ref("job-1", report)
    assert (ref.job_id, ref.risk_score, ref.risk_level) == (
        "job-1",
        report.risk_score,
        report.risk_level.value,
    )
    assert ref.ai_analysis_available is report.ai_analysis_available
    assert ref.analyzed_at == report.meta.analyzed_at
