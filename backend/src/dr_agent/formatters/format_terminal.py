"""DRReadinessReport -> Rich-rendered terminal output.

Renders to the given `Console` (or an internal string buffer, returned as
plain text with no ANSI codes when not a real terminal -- this is what keeps
formatter tests deterministic snapshots). The CLI (Phase 5) passes a real
stdout `Console` to get color in an actual terminal.
"""

from __future__ import annotations

import io

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from dr_agent.models.insights import ServiceHistory
from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DRReadinessReport, RiskLevel

_RISK_STYLES = {
    RiskLevel.LOW: "bold green",
    RiskLevel.MEDIUM: "bold yellow",
    RiskLevel.HIGH: "bold dark_orange",
    RiskLevel.CRITICAL: "bold red",
}
_DEPENDENCY_STYLES = {
    DependencyStatus.UP: "green",
    DependencyStatus.DOWN: "red",
    DependencyStatus.UNREACHABLE: "red",
    DependencyStatus.NOT_IN_INVENTORY: "yellow",
}
_SEVERITY_STYLES = {"HIGH": "bold red", "MEDIUM": "yellow", "LOW": "dim"}


def render_terminal(report: DRReadinessReport, *, console: Console | None = None) -> str:
    buffer = io.StringIO()
    target = console or Console(file=buffer, width=100)

    target.print(f"[bold]{report.service_summary.name}[/bold] readiness report")
    target.print(report.summary)
    target.print()
    score_text = f"{report.risk_score}/100 ({report.risk_level.value})"
    target.print(Text.assemble("Risk score: ", (score_text, _RISK_STYLES[report.risk_level])))
    if not report.ai_analysis_available and report.ai_note:
        target.print(f"[yellow]{report.ai_note}[/yellow]")
    target.print()

    rto = report.rto_analysis
    feasibility = "[green]feasible[/green]" if rto.feasible else "[red]NOT feasible[/red]"
    target.print(
        f"RTO: {feasibility} -- {rto.total_estimated_minutes:g} min estimated vs "
        f"{rto.stated_rto_minutes:g} min stated (buffer {rto.buffer_minutes:+g} min)"
    )
    if rto.bottleneck_steps:
        target.print(f"Bottleneck steps: {', '.join(str(n) for n in rto.bottleneck_steps)}")
    target.print()

    if report.dependency_health:
        target.print(_dependency_table(report))
        target.print()

    if report.gap_analysis:
        target.print(_gap_table(report))
        target.print()

    if report.single_points_of_failure:
        target.print("[bold]Single points of failure[/bold]")
        for spof in report.single_points_of_failure:
            target.print(f"  - {spof.description} ({spof.mitigation_suggestion})")
        target.print()

    if report.suggestions:
        target.print("[bold]Suggestions[/bold]")
        for suggestion in sorted(report.suggestions, key=lambda s: s.priority):
            target.print(f"  [P{suggestion.priority}] {suggestion.title}: {suggestion.detail}")

    if report.historical_insights is not None:
        target.print()
        _print_history(target, report.historical_insights)

    return buffer.getvalue()


def _print_history(target: Console, history: ServiceHistory) -> None:
    target.print("[bold]Historical insights[/bold]")
    target.print(
        f"  {history.live_runs} live run(s), {history.analyses_considered} earlier analysis(es), "
        f"{history.dry_runs} dry run(s) not measured"
    )
    for step in history.steps:
        median = step.median_active_minutes
        timing = f"median {median:g} min vs {step.estimated_minutes:g} estimated" if median else ""
        target.print(
            f"  Step {step.step_number}: {step.live_runs} run(s), failed {step.failed}, "
            f"rolled back {step.rolled_back}{'; ' + timing if timing else ''}"
        )


def _dependency_table(report: DRReadinessReport) -> Table:
    table = Table(title="Dependency health", box=box.ASCII)
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Impact")
    for dep in report.dependency_health:
        style = _DEPENDENCY_STYLES[dep.actual_status]
        table.add_row(dep.name, f"[{style}]{dep.actual_status.value}[/{style}]", dep.impact)
    return table


def _gap_table(report: DRReadinessReport) -> Table:
    table = Table(title="Gaps", box=box.ASCII)
    table.add_column("Type")
    table.add_column("Severity")
    table.add_column("Description")
    for gap in report.gap_analysis:
        style = _SEVERITY_STYLES[gap.severity.value]
        table.add_row(gap.type.value, f"[{style}]{gap.severity.value}[/{style}]", gap.description)
    return table
