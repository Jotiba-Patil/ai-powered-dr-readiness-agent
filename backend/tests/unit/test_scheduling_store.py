"""SQLite schedule store: round trip, claiming once per slot, pauses, runs, restarts."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from history_support import make_record
from scheduling_support import T0, hourly, ids

from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.scheduling.models import (
    EmailState,
    RunState,
    RunTrigger,
    Schedule,
    ScheduleRun,
)
from dr_agent.scheduling.runner import next_slot
from dr_agent.scheduling.sqlite_store import SqliteScheduleStore
from dr_agent.utils.errors import ConflictError, NotFoundError

FIRST_SLOT = T0 + timedelta(minutes=15)


def schedule(schedule_id: str = "s1", **update: object) -> Schedule:
    base = Schedule.model_validate(
        {
            **hourly(recipients=["a@example.com"]).model_dump(),
            "id": schedule_id,
            "created_by": "Alice",
            "created_at": T0,
            "updated_at": T0,
            "next_run_at": FIRST_SLOT,
        }
    )
    return base.model_copy(update=update)


async def store_with(path: Path, *schedules: Schedule) -> SqliteScheduleStore:
    store = await SqliteScheduleStore.open(path / "s.db")
    for item in schedules:
        await store.create(item)
    return store


async def test_round_trip_and_list(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule("s1"), schedule("s2"))
    assert await store.get("s1") == schedule("s1")
    assert [s.id for s in await store.list_all()] == ["s1", "s2"]
    changed = schedule("s1", name="Renamed", enabled=False, next_run_at=None)
    await store.update(changed)
    assert await store.get("s1") == changed
    await store.delete("s2")
    with pytest.raises(NotFoundError):
        await store.get("s2")
    with pytest.raises(NotFoundError):
        await store.update(schedule("nope"))
    with pytest.raises(NotFoundError):
        await store.delete("nope")


async def test_a_slot_is_claimed_once(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    new_id = ids("r")
    assert await store.claim_due(T0, next_slot, new_id) == []  # 05:15 is not due yet
    at = T0 + timedelta(minutes=16)
    [run] = await store.claim_due(at, next_slot, new_id)
    assert (run.slot_at, run.trigger, run.state) == (
        T0 + timedelta(minutes=15),
        RunTrigger.SCHEDULED,
        RunState.RUNNING,
    )
    assert await store.claim_due(at, next_slot, new_id) == []
    moved = await store.get("s1")
    assert moved.next_run_at == T0 + timedelta(hours=1, minutes=15)
    assert moved.last_run_at == at


async def test_missed_slots_run_once_then_continue_from_now(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    later = T0 + timedelta(hours=5, minutes=1)  # five slots missed while "down"
    runs = await store.claim_due(later, next_slot, ids("r"))
    assert len(runs) == 1
    assert (await store.get("s1")).next_run_at == T0 + timedelta(hours=5, minutes=15)


async def test_a_running_run_skips_the_next_slot(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    new_id = ids("r")
    await store.claim_due(T0 + timedelta(minutes=16), next_slot, new_id)
    skipped = await store.claim_due(T0 + timedelta(hours=1, minutes=16), next_slot, new_id)
    assert skipped == []
    assert (await store.get("s1")).next_run_at == T0 + timedelta(hours=2, minutes=15)


async def test_manual_runs_and_run_records(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    run = await store.start_manual("s1", T0, "m1")
    assert run.trigger is RunTrigger.MANUAL
    with pytest.raises(ConflictError):
        await store.start_manual("s1", T0 + timedelta(seconds=1), "m2")
    with pytest.raises(NotFoundError):
        await store.start_manual("nope", T0, "m3")
    done = run.model_copy(
        update={
            "state": RunState.FAILED,
            "finished_at": T0,
            "email_state": EmailState.SENT,
            "email_to": ["a@example.com", "b@example.com"],
            "error_code": "PARSE_ERROR",
            "error": "bad",
        }
    )
    await store.save_run(done)
    assert await store.get_run("m1") == done
    second = await store.start_manual("s1", T0 + timedelta(minutes=1), "m2")
    assert [r.id for r in await store.list_runs("s1", limit=10)] == ["m2", "m1"]
    assert [r.id for r in await store.list_runs("s1", limit=10, before=second.started_at)] == ["m1"]
    assert (await store.latest_runs())["s1"].id == "m2"
    with pytest.raises(NotFoundError):
        await store.get_run("nope")


async def test_restart_marks_running_runs_interrupted(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    await store.start_manual("s1", T0, "m1")
    assert await store.fail_interrupted(T0 + timedelta(minutes=5)) == 1
    run = await store.get_run("m1")
    assert (run.state, run.error_code) == (RunState.FAILED, "INTERRUPTED")
    assert await store.fail_interrupted(T0) == 0


async def test_deleting_a_schedule_deletes_its_runs(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    await store.start_manual("s1", T0, "m1")
    await store.delete("s1")
    with pytest.raises(NotFoundError):
        await store.get_run("m1")


async def test_run_linked_to_a_deleted_analysis_keeps_the_run(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    analyses = await SqliteAnalysisStore.open(tmp_path / "s.db")
    await analyses.save(make_record("job1"))
    run: ScheduleRun = await store.start_manual("s1", T0, "m1")
    await store.save_run(run.model_copy(update={"job_id": "job1", "analysis_id": "job1"}))
    await analyses.delete("job1")
    kept = await store.get_run("m1")
    assert (kept.job_id, kept.analysis_id) == ("job1", None)


async def test_a_slot_with_a_run_already_recorded_is_skipped(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    earlier = ScheduleRun(
        id="old",
        schedule_id="s1",
        slot_at=FIRST_SLOT,
        trigger=RunTrigger.SCHEDULED,
        state=RunState.SUCCEEDED,
        started_at=FIRST_SLOT,
    )
    await store.save_run(earlier)
    assert await store.claim_due(FIRST_SLOT + timedelta(minutes=1), next_slot, ids("r")) == []
    assert (await store.get("s1")).next_run_at == FIRST_SLOT + timedelta(hours=1)


async def test_a_failing_claim_changes_nothing(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())

    def broken(_: Schedule, __: object) -> object:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        await store.claim_due(FIRST_SLOT + timedelta(minutes=1), broken, ids("r"))  # type: ignore[arg-type]  # deliberately broken
    assert (await store.get("s1")).next_run_at == FIRST_SLOT
    assert await store.list_runs("s1", limit=5) == []
