"""What `dr-agent execute` prints before asking: the readiness summary and history state."""

from __future__ import annotations

from rich.console import Console

from dr_agent.cli_analysis import CliAnalysis
from dr_agent.models.report import DRReadinessReport


def show_analysis(console: Console, report: DRReadinessReport) -> None:
    rto = report.rto_analysis
    phases = " -> ".join("+".join(map(str, p.steps)) for p in report.execution_plan)
    feasible = "feasible" if rto.feasible else "NOT feasible"
    console.print(
        f"Readiness: risk [bold]{report.risk_score}[/] ({report.risk_level.value}); "
        f"RTO {feasible} ({rto.total_estimated_minutes:g} of {rto.stated_rto_minutes:g} min); "
        f"{len(report.gap_analysis)} gap(s); plan {phases}"
        + ("" if report.ai_analysis_available else " [yellow](rule-based only)[/]")
    )
    history = report.historical_insights
    if history is not None:
        console.print(
            f"History: {history.live_runs} live run(s), {history.analyses_considered} "
            f"earlier analysis(es); {len(history.steps)} step(s) matched this runbook"
        )


def show_history_state(console: Console, analysis: CliAnalysis) -> None:
    record = analysis.record
    if analysis.stale:
        console.print(
            f"[yellow]Analysis {record.id} is from {record.completed_at:%Y-%m-%d %H:%M} UTC; "
            "dependency health may have changed since. Consider analyzing again.[/]"
        )
    elif analysis.saved:
        console.print(f"Analysis {record.id} (stored in the history)")
