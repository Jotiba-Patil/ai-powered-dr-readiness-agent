"""`dr-agent schedule list|runs`: read-only view of schedules (design scheduled-analysis 10).

Schedules are created and changed in the API or dashboard, because the scheduler
runs in the API process and must see changes at once. To execute a scheduled
run, pass its analysis id to `dr-agent execute --analysis ID`.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Annotated

import typer

from dr_agent.cli_common import VerboseOpt, run_or_exit, startup
from dr_agent.config import Settings
from dr_agent.scheduling.models import Schedule, SchedulerState, ScheduleRun
from dr_agent.scheduling.next_run import describe
from dr_agent.scheduling.sqlite_store import SqliteScheduleStore
from dr_agent.utils.timefmt import display_time

schedule_app = typer.Typer(
    help="Scheduled analyses: list schedules and their runs (read-only).", no_args_is_help=True
)

IdArg = Annotated[str, typer.Argument(help="Schedule id (see `dr-agent schedule list`).")]


@schedule_app.command("list")
def list_schedules(verbose: VerboseOpt = False) -> None:
    """Schedules with their next slot and latest run."""
    settings = startup(verbose)
    schedules, latest, state = run_or_exit(_overview(settings))
    zone = settings.display_zone
    if not settings.scheduler_enabled:
        typer.echo("Note: SCHEDULER_ENABLED=false, so nothing runs on this server.", err=True)
    if state.paused:
        until = f" until {_at(state.pause_until, zone)}" if state.pause_until else ""
        typer.echo(f"All schedules are paused{until} (by {state.paused_by}).")
    if not schedules:
        typer.echo("No schedules.")
        return
    for schedule in schedules:
        typer.echo(
            f"{schedule.id}  {schedule.name}  {describe(schedule.cadence, schedule.timezone)}  "
            f"{_state(schedule, zone)}  last: {_run_line(latest.get(schedule.id))}"
        )


@schedule_app.command("runs")
def list_runs(
    schedule_id: IdArg,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=100)] = 20,
    verbose: VerboseOpt = False,
) -> None:
    """Runs of one schedule, newest first, with the analysis id to execute."""
    settings = startup(verbose)
    runs = run_or_exit(_runs(settings, schedule_id, limit))
    if not runs:
        typer.echo("No runs yet.")
        return
    for run in runs:
        analysis = f"analysis {run.analysis_id}" if run.analysis_id else "not stored"
        typer.echo(
            f"{run.id}  {_at(run.started_at, settings.display_zone)}  {run.trigger.value}  "
            f"{_run_line(run)}  {analysis}"
        )


def _state(schedule: Schedule, zone: tzinfo | None) -> str:
    if schedule.enabled:
        return f"next {_at(schedule.next_run_at, zone)}" if schedule.next_run_at else "active"
    until = f" until {_at(schedule.pause_until, zone)}" if schedule.pause_until else ""
    return f"paused{until} by {schedule.paused_by}"


def _run_line(run: ScheduleRun | None) -> str:
    if run is None:
        return "never run"
    email = f"email {run.email_state.value}" if run.email_state else "email -"
    if run.risk_score is not None and run.risk_level is not None:
        rto = "RTO feasible" if run.rto_feasible else "RTO NOT feasible"
        return f"{run.state.value}, risk {run.risk_score} {run.risk_level.value}, {rto}, {email}"
    reason = f" ({run.error_code})" if run.error_code else ""
    return f"{run.state.value}{reason}, {email}"


def _at(value: datetime | None, zone: tzinfo | None) -> str:
    return display_time(value, zone) if value else "-"


async def _overview(
    settings: Settings,
) -> tuple[list[Schedule], dict[str, ScheduleRun], SchedulerState]:
    store = await SqliteScheduleStore.open(settings.database_path)
    return await store.list_all(), await store.latest_runs(), await store.get_state()


async def _runs(settings: Settings, schedule_id: str, limit: int) -> list[ScheduleRun]:
    store = await SqliteScheduleStore.open(settings.database_path)
    await store.get(schedule_id)  # NotFoundError for an unknown id
    return await store.list_runs(schedule_id, limit=limit)
