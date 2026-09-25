"""`dr-agent` command-line interface (Typer).

Exit codes (per the brief): 0 success, 1 error (including usage errors), 2 the
analysis succeeded but the risk score is critical (> 80); for `execute`, 2 means
the execution failed or was aborted. Reports go to stdout
(or `--output`); logs, the spinner and errors go to stderr so stdout can be piped.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console

from dr_agent import __version__
from dr_agent.cli_analysis import CliAnalysis, run_analysis
from dr_agent.cli_common import (
    EXIT_CRITICAL,
    EXIT_ERROR,
    EXIT_OK,
    VerboseOpt,
    fail,
    run_or_exit,
    startup,
)
from dr_agent.cli_execute import LiveOpt, OperatorOpt, execute_runbook, exit_code
from dr_agent.cli_history import history_app
from dr_agent.cli_output import HealthFormat, ReportFormat, render_report, write_output
from dr_agent.config import Settings
from dr_agent.formatters.format_health import format_health_json, render_health_terminal
from dr_agent.loaders import load_inventory, read_text_file
from dr_agent.models.inventory import ServiceStatus
from dr_agent.service import parse_markdown, validate_inventory
from dr_agent.utils.errors import AppError
from dr_agent.wiring import build_checker, build_llm

__all__ = ["EXIT_CRITICAL", "EXIT_ERROR", "EXIT_OK", "app", "main", "run"]
CRITICAL_RISK_THRESHOLD = 80


app = typer.Typer(
    name="dr-agent",
    help="AI-powered DR readiness agent: parse, validate, analyze and execute DR runbooks.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
app.add_typer(history_app, name="history")

RunbookOpt = Annotated[Path, typer.Option("--runbook", "-r", help="Markdown runbook path.")]
InventoryOpt = Annotated[Path, typer.Option("--inventory", "-i", help="Inventory JSON path.")]
ChaosOpt = Annotated[bool, typer.Option("--chaos", help="Randomly fail ~20% of mock checks.")]
NoSaveOpt = Annotated[
    bool, typer.Option("--no-save", help="Do not store this analysis in the history.")
]


@app.command()
def analyze(
    runbook: RunbookOpt,
    inventory: Annotated[
        Path | None, typer.Option("--inventory", "-i", help="Inventory JSON path.")
    ] = None,
    output_format: Annotated[ReportFormat, typer.Option("--format", "-f")] = ReportFormat.TERMINAL,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write to file.")] = None,
    chaos: ChaosOpt = False,
    no_save: NoSaveOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Parse, health-check and analyze a runbook into a readiness report (stored by default)."""
    settings = startup(verbose)
    analysis = run_or_exit(_analyze(settings, runbook, inventory, chaos, save=not no_save))
    report = analysis.record.report
    if analysis.saved:
        typer.echo(f"Saved to history as {analysis.record.id}", err=True)
    try:
        write_output(render_report(report, output_format, to_file=output is not None), output)
    except AppError as exc:
        fail(exc)
    if report.risk_score > CRITICAL_RISK_THRESHOLD:
        raise typer.Exit(EXIT_CRITICAL)


@app.command()
def validate(
    inventory: InventoryOpt,
    output_format: Annotated[HealthFormat, typer.Option("--format", "-f")] = HealthFormat.TERMINAL,
    chaos: ChaosOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Only run health checks for every service in an inventory."""
    settings = startup(verbose)
    statuses = run_or_exit(_validate(settings, inventory, chaos))
    if output_format is HealthFormat.JSON:
        typer.echo(format_health_json(statuses))
    else:
        render_health_terminal(statuses, console=Console())


@app.command()
def parse(runbook: RunbookOpt, verbose: VerboseOpt = False) -> None:
    """Only parse a runbook (no health checks, no AI) and print it as JSON."""
    startup(verbose)
    try:
        parsed = parse_markdown(read_text_file(runbook))
    except AppError as exc:
        fail(exc)
    data = parsed.model_dump(mode="json", by_alias=True, exclude={"raw_markdown"})
    typer.echo(json.dumps(data, indent=2))


@app.command()
def execute(
    operator: OperatorOpt,
    runbook: Annotated[Path | None, typer.Option("--runbook", "-r")] = None,
    analysis: Annotated[
        str | None, typer.Option("--analysis", "-a", help="Execute a stored analysis instead.")
    ] = None,
    inventory: Annotated[Path | None, typer.Option("--inventory", "-i")] = None,
    live: LiveOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Analyze a runbook (or load a stored analysis), then, if you agree, carry out its steps."""
    if (runbook is None) == (analysis is None):
        raise typer.BadParameter("give either --runbook or --analysis")
    settings = startup(verbose)
    final = run_or_exit(
        execute_runbook(
            settings,
            runbook,
            analysis_id=analysis,
            inventory_path=inventory,
            operator=operator,
            live=live,
            ask=typer.prompt,
            confirm=typer.confirm,
            console=Console(),
        )
    )
    raise typer.Exit(exit_code(final))


@app.command()
def version() -> None:
    """Print the agent version."""
    typer.echo(f"dr-agent {__version__}")


async def _analyze(
    settings: Settings, runbook_path: Path, inventory_path: Path | None, chaos: bool, *, save: bool
) -> CliAnalysis:
    async with httpx.AsyncClient() as client:
        rng = random.Random()  # noqa: S311 -- simulated latency/jitter, not security
        with Console(stderr=True).status("Analyzing runbook (an LLM on CPU can take minutes)"):
            return await run_analysis(
                settings,
                runbook_path,
                inventory_path,
                llm=build_llm(settings, client, rng),
                checker=build_checker(settings, client, rng, chaos=chaos or None),
                save=save,
            )


async def _validate(settings: Settings, inventory_path: Path, chaos: bool) -> list[ServiceStatus]:
    inventory = load_inventory(inventory_path)
    async with httpx.AsyncClient() as client:
        rng = random.Random()  # noqa: S311 -- simulated latency/jitter, not security
        checker = build_checker(settings, client, rng, chaos=chaos or None)
        return await validate_inventory(inventory, checker)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its exit code; usage errors map to 1, not Click's 2."""
    try:
        result = app(args=argv, prog_name="dr-agent", standalone_mode=False)
    except typer.Abort:
        return EXIT_ERROR
    except typer.TyperException as exc:  # usage errors (Typer vendors its own Click)
        if message := exc.format_message():  # empty when help was shown (no arguments)
            typer.echo(f"Error: {message} (try 'dr-agent --help')", err=True)
        return EXIT_ERROR
    return result if isinstance(result, int) else EXIT_OK


def run() -> None:
    """Console-script entry point (`dr-agent`)."""
    sys.exit(main())
