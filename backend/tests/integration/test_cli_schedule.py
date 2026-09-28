"""`dr-agent schedule list|runs`: read-only view of the schedules in the database."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dr_agent import cli
from dr_agent.models.report import RiskLevel
from dr_agent.scheduling.models import (
    EmailState,
    HourlyCadence,
    RunState,
    RunTrigger,
    Schedule,
    SchedulerState,
    ScheduleRun,
)
from dr_agent.scheduling.sqlite_store import SqliteScheduleStore

T0 = datetime(2026, 9, 27, 5, 0, tzinfo=UTC)
runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env from the repository
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)


def schedule(schedule_id: str, **update: object) -> Schedule:
    base = Schedule(
        id=schedule_id,
        name=f"Estimate {schedule_id}",
        runbook_path="runbooks/estimate-service.md",
        cadence=HourlyCadence(minute=15),
        created_by="Alice",
        created_at=T0,
        updated_at=T0,
        next_run_at=T0 + timedelta(minutes=15),
    )
    return base.model_copy(update=update)


async def seed(db: Path) -> None:
    store = await SqliteScheduleStore.open(db)
    await store.create(schedule("s1"))
    await store.create(schedule("s2", enabled=False, next_run_at=None, paused_by="Bob"))
    ok = ScheduleRun(
        id="r1",
        schedule_id="s1",
        slot_at=T0,
        trigger=RunTrigger.SCHEDULED,
        state=RunState.SUCCEEDED,
        started_at=T0,
        risk_score=35,
        risk_level=RiskLevel.MEDIUM,
        rto_feasible=True,
        email_state=EmailState.SENT,
    )
    await store.save_run(ok)
    failed = ok.model_copy(
        update={
            "id": "r2",
            "slot_at": T0 + timedelta(hours=1),
            "started_at": T0 + timedelta(hours=1),
            "state": RunState.FAILED,
            "risk_score": None,
            "risk_level": None,
            "rto_feasible": None,
            "error_code": "PARSE_ERROR",
        }
    )
    await store.save_run(failed)
    await store.pause_all(SchedulerState(paused=True, paused_by="Bob", paused_at=T0))


def test_list_and_runs(isolated_database: Path) -> None:
    asyncio.run(seed(isolated_database))
    listed = runner.invoke(cli.app, ["schedule", "list"])
    assert listed.exit_code == 0, listed.output
    assert "SCHEDULER_ENABLED=false" in listed.stderr
    assert "All schedules are paused (by Bob)." in listed.stdout
    assert "s1  Estimate s1  Hourly at :15 UTC  next 27 Sep 2026, 05:15 UTC" in listed.stdout
    assert "last: failed (PARSE_ERROR), email sent" in listed.stdout
    assert "s2  Estimate s2  Hourly at :15 UTC  paused by Bob  last: never run" in listed.stdout
    runs = runner.invoke(cli.app, ["schedule", "runs", "s1"])
    assert runs.exit_code == 0, runs.output
    lines = runs.stdout.strip().splitlines()
    assert lines[0].startswith("r2  27 Sep 2026, 06:00 UTC  scheduled  failed (PARSE_ERROR)")
    assert "succeeded, risk 35 MEDIUM, RTO feasible, email sent  not stored" in lines[1]
    assert runner.invoke(cli.app, ["schedule", "runs", "s2"]).stdout.strip() == "No runs yet."


def test_times_follow_display_timezone(
    isolated_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(seed(isolated_database))
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Asia/Kolkata")
    listed = runner.invoke(cli.app, ["schedule", "list"])
    assert "next 27 Sep 2026, 10:45 UTC+05:30" in listed.stdout
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Mars/Olympus")
    bad = runner.invoke(cli.app, ["schedule", "list"])
    assert bad.exit_code == 1
    assert "DISPLAY_TIMEZONE" in bad.stderr


def test_empty_and_unknown(isolated_database: Path) -> None:
    empty = runner.invoke(cli.app, ["schedule", "list"])
    assert empty.stdout.strip() == "No schedules."
    missing = runner.invoke(cli.app, ["schedule", "runs", "nope"])
    assert missing.exit_code == 1
    assert "not found" in missing.stderr
