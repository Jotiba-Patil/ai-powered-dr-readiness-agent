"""Historical insights in the terminal and HTML reports and the `execute` step panels."""

from __future__ import annotations

from pathlib import Path

from exec_support import drsim_catalog, drsim_policy, executable_runbook
from rich.console import Console

from dr_agent.cli_execute_steps import previous_runs, show_step
from dr_agent.cli_execute_view import show_analysis
from dr_agent.execution.models import ExecutionMode
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.formatters.format_html import format_html
from dr_agent.formatters.format_terminal import render_terminal
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.report import DRReadinessReport

ROOT = Path(__file__).resolve().parents[3]
HISTORY = ServiceHistory.model_validate_json(
    (ROOT / "backend/tests/fixtures/history/estimate-service.json").read_text("utf-8")
)
WITH_HISTORY = DRReadinessReport.model_validate_json(
    (ROOT / "mock-data/expected-reports/estimate-service-history.json").read_text("utf-8")
)


def test_terminal_report_shows_the_history() -> None:
    text = render_terminal(WITH_HISTORY)
    assert "Historical insights" in text
    assert "4 live run(s), 6 earlier analysis(es), 2 dry run(s) not measured" in text
    assert "Step 3: 4 run(s), failed 1, rolled back 1; median 12 min vs 10 estimated" in text


def test_html_report_shows_the_history() -> None:
    html = format_html(WITH_HISTORY)
    assert "<h2>Historical insights</h2>" in html
    assert "COMPLETED in 80.0 min" in html
    assert "(stated RTO 60.0 min)" in html


def test_reports_without_history_have_no_section(sample_report: DRReadinessReport) -> None:
    assert "Historical insights" not in render_terminal(sample_report)
    assert "Historical insights" not in format_html(sample_report)


def test_execute_shows_previous_runs() -> None:
    console = Console(record=True, width=200)
    show_analysis(console, WITH_HISTORY)
    step3 = next(s for s in HISTORY.steps if s.step_number == 3)
    execution, _ = plan_execution(
        executable_runbook(),
        policy=drsim_policy(),
        catalog=index_catalog(drsim_catalog()),
        execution_id="e",
        mode=ExecutionMode.DRY_RUN,
        started_by="Olivia",
        runbook_label="x",
        now=WITH_HISTORY.meta.analyzed_at,
    )
    show_step(console, execution.step(3), step3)
    text = console.export_text()
    assert "History: 4 live run(s), 6 earlier analysis(es); 5 step(s) matched this runbook" in text
    assert "Previous live runs: 4, failed 1, rolled back 1, median 12 min" in text
    no_timing = step3.model_copy(update={"median_active_minutes": None})
    assert previous_runs(no_timing).endswith("rolled back 1[/]")
