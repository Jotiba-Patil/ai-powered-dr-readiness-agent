"""SQLite store: round trips, projections, chain continuity, errors."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from exec_support import OPERATOR, drsim_catalog, drsim_policy, executable_runbook

from dr_agent.execution.audit import AuditEvent, verify_chain
from dr_agent.execution.journal import Journal
from dr_agent.execution.models import Execution, ExecutionMode
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.execution.transitions import ExecutionEvent
from dr_agent.storage.migrations import LATEST_VERSION
from dr_agent.utils.errors import ConflictError, NotFoundError

NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _new(execution_id: str = "exec-1", now: datetime = NOW) -> tuple[Execution, list[AuditEvent]]:
    return plan_execution(
        executable_runbook(),
        policy=drsim_policy(),
        catalog=index_catalog(drsim_catalog()),
        execution_id=execution_id,
        mode=ExecutionMode.LIVE,
        started_by=OPERATOR,
        runbook_label="sample",
        now=now,
    )


async def _store(tmp_path: Path) -> SqliteExecutionStore:
    return await SqliteExecutionStore.open(tmp_path / "x.db")


async def test_round_trip_and_audit(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    execution, events = _new()
    await store.create(execution, events)
    loaded = await store.get("exec-1")
    assert loaded == execution
    audit = await store.audit("exec-1")
    assert audit == events
    assert verify_chain("exec-1", audit).valid


async def test_save_appends_events_and_updates_projections(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    execution, events = _new()
    await store.create(execution, events)
    journal = Journal(execution, NOW)
    journal.move_execution(ExecutionEvent.START, OPERATOR)
    await store.save(execution, journal.events)
    assert (await store.get("exec-1")).state.value == "RUNNING"
    assert len(await store.audit("exec-1")) == len(events) + 1

    with closing(sqlite3.connect(tmp_path / "x.db")) as conn, conn:
        state = conn.execute("SELECT state FROM executions").fetchone()[0]
        steps = conn.execute("SELECT COUNT(*) FROM step_runs").fetchone()[0]
        calls = conn.execute("SELECT kind, COUNT(*) FROM tool_calls GROUP BY kind").fetchall()
    assert state == "RUNNING"
    assert steps == 5
    assert dict(calls) == {"main": 5, "verify": 4, "rollback": 2}


async def test_events_must_continue_the_stored_chain(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    execution, events = _new()
    await store.create(execution, events)
    stale: Execution = execution.model_copy(deep=True)
    first = Journal(execution, NOW)
    first.move_execution(ExecutionEvent.START, OPERATOR)
    await store.save(execution, first.events)
    second = Journal(stale, NOW)
    second.move_execution(ExecutionEvent.ABORT, OPERATOR, "late writer")
    with pytest.raises(ConflictError, match="changed concurrently"):
        await store.save(stale, second.events)
    assert (await store.get("exec-1")).state.value == "RUNNING"


async def test_list_is_newest_first(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    for n, day in ((1, 1), (2, 3), (3, 2)):
        await store.create(*_new(f"exec-{n}", NOW.replace(day=day)))
    assert [e.id for e in await store.list_all()] == ["exec-2", "exec-3", "exec-1"]


async def test_errors(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    execution, events = _new()
    with pytest.raises(NotFoundError):
        await store.save(execution, events)
    await store.create(execution, events)
    with pytest.raises(ConflictError, match="already exists"):
        await store.create(execution, [])
    with pytest.raises(NotFoundError):
        await store.get("nope")
    with pytest.raises(NotFoundError):
        await store.audit("nope")


async def test_reopening_keeps_data_and_schema_version(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await store.create(*_new())
    reopened = await _store(tmp_path)
    assert (await reopened.get("exec-1")).id == "exec-1"
    with closing(sqlite3.connect(tmp_path / "x.db")) as conn, conn:
        assert conn.execute("SELECT version FROM schema_version").fetchall() == [(LATEST_VERSION,)]
