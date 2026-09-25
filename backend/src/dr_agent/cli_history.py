"""`dr-agent history list|show|delete`: stored analyses (design analysis-history section 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from dr_agent.cli_analysis import require_history
from dr_agent.cli_common import VerboseOpt, fail, run_or_exit, startup
from dr_agent.cli_output import ReportFormat, render_report, write_output
from dr_agent.config import Settings
from dr_agent.history.models import MAX_PAGE, AnalysisQuery, AnalysisRecord, AnalysisSummary
from dr_agent.utils.errors import AppError

history_app = typer.Typer(help="Stored analyses: list, show and delete.", no_args_is_help=True)

IdArg = Annotated[str, typer.Argument(help="Analysis id (see `dr-agent history list`).")]


@history_app.command("list")
def list_analyses(
    service: Annotated[str | None, typer.Option("--service", "-s")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=MAX_PAGE)] = 20,
    verbose: VerboseOpt = False,
) -> None:
    """Stored analyses, newest first."""
    settings = startup(verbose)
    items = run_or_exit(_list(settings, AnalysisQuery(service=service, limit=limit)))
    if not items:
        typer.echo("No stored analyses.")
        return
    # One plain line per analysis: the id stays whole and the output can be piped.
    for item in items:
        rto = "RTO feasible" if item.rto_feasible else "RTO NOT feasible"
        typer.echo(
            f"{item.id}  {item.completed_at:%Y-%m-%d %H:%M} UTC  {item.service_name}  "
            f"risk {item.risk_score} {item.risk_level.value}  {rto}  "
            f"runs {item.execution_count}  {item.source.value}"
        )


@history_app.command("show")
def show(
    analysis_id: IdArg,
    output_format: Annotated[ReportFormat, typer.Option("--format", "-f")] = ReportFormat.TERMINAL,
    runbook: Annotated[
        bool, typer.Option("--runbook", help="Print the stored runbook Markdown instead.")
    ] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write to file.")] = None,
    verbose: VerboseOpt = False,
) -> None:
    """Show a stored report (or its runbook)."""
    settings = startup(verbose)
    record = run_or_exit(_get(settings, analysis_id))
    try:
        if runbook:
            write_output(record.runbook.raw_markdown, output)
        else:
            to_file = output is not None
            write_output(render_report(record.report, output_format, to_file=to_file), output)
    except AppError as exc:
        fail(exc)


@history_app.command("delete")
def delete(
    analysis_id: IdArg,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
    verbose: VerboseOpt = False,
) -> None:
    """Delete a stored analysis (refused while executions refer to it)."""
    settings = startup(verbose)
    if not yes and not typer.confirm(f"Delete analysis {analysis_id} and its runbook?"):
        typer.echo("Not deleted.")
        return
    run_or_exit(_delete(settings, analysis_id))
    typer.echo(f"Deleted analysis {analysis_id}.")


async def _list(settings: Settings, query: AnalysisQuery) -> list[AnalysisSummary]:
    return await (await require_history(settings)).store.list_page(query)


async def _get(settings: Settings, analysis_id: str) -> AnalysisRecord:
    return await (await require_history(settings)).store.get(analysis_id)


async def _delete(settings: Settings, analysis_id: str) -> None:
    await (await require_history(settings)).store.delete(analysis_id)
