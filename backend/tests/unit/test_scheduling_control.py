"""Scheduler control: cancel, shutdown and restart, the ticker, and the no-execution rule."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from scheduling_support import due_run, hourly, make_rig, started_run

from dr_agent.scheduling.models import RunState, ScheduleRun
from dr_agent.storage.sqlite import connect
from dr_agent.utils.errors import ConflictError

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "dr_agent"


async def test_cancel_stops_the_analysis_and_sends_no_email(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    run = await started_run(rig)
    cancelled = await rig.service.cancel_run(run.id)
    assert cancelled.state is RunState.CANCELLED
    assert cancelled.finished_at is not None
    assert rig.analyze.cancelled == ["job1"]
    assert not rig.notifier.sent
    with pytest.raises(ConflictError):
        await rig.service.cancel_run(run.id)


async def test_cancel_of_a_run_without_a_task_closes_it(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await rig.service.create(hourly(), created_by="Alice")
    await rig.store.start_manual("s1", rig.clock(), "orphan")
    assert (await rig.service.cancel_run("orphan")).state is RunState.CANCELLED


async def test_shutdown_interrupts_a_run_and_recover_closes_leftovers(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    run = await started_run(rig)
    await rig.scheduler.shutdown()
    stopped = await rig.store.get_run(run.id)
    assert (stopped.state, stopped.error_code) == (RunState.FAILED, "INTERRUPTED")
    await rig.store.start_manual("s1", rig.clock.advance(seconds=1), "left-over")
    assert await rig.scheduler.recover() == 1


async def test_deleting_a_schedule_cancels_its_running_run(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await started_run(rig)
    await rig.service.delete("s1")
    assert rig.analyze.cancelled == ["job1"]
    assert await rig.store.list_all() == []


async def test_ticker_starts_due_runs_and_survives_errors(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await rig.service.create(hourly(), created_by="Alice")
    rig.clock.advance(minutes=16)
    real_claim = rig.store.claim_due
    calls = 0

    async def flaky(*args: object) -> list[ScheduleRun]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk busy")
        return await real_claim(*args)  # type: ignore[arg-type]  # same signature

    rig.store.claim_due = flaky  # type: ignore[method-assign]  # one failing tick
    rig.scheduler._tick_seconds = 0
    rig.scheduler.start()
    while not await rig.store.list_runs("s1", limit=1):
        await asyncio.sleep(0)
    await rig.scheduler.wait_idle()
    await rig.scheduler.shutdown()
    [run] = await rig.store.list_runs("s1", limit=5)
    assert run.state is RunState.SUCCEEDED
    assert calls >= 2


async def test_scheduled_runs_never_create_executions(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await due_run(rig)
    with connect(tmp_path / "db.sqlite") as conn:
        assert conn.execute("SELECT COUNT(*) FROM executions").fetchone() == (0,)
    for package in ("scheduling", "notify"):
        for source in (PACKAGE / package).glob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "dr_agent.execution" not in text, source.name
            assert "fastapi" not in text.lower(), source.name
