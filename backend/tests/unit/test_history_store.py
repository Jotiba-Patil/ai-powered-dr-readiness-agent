"""SQLite analysis store: round trip, filters, pagination, delete and retention."""

from __future__ import annotations

from pathlib import Path

import pytest
from history_support import T0, make_record, store_execution

from dr_agent.history.models import AnalysisQuery, AnalysisSource
from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.models.report import RiskLevel
from dr_agent.storage.sqlite import connect
from dr_agent.utils.errors import ConflictError, NotFoundError, ValidationError


async def _store(path: Path) -> SqliteAnalysisStore:
    return await SqliteAnalysisStore.open(path)


async def test_round_trip_keeps_everything(tmp_path: Path) -> None:
    store = await _store(tmp_path / "h.db")
    record = make_record()
    await store.save(record)
    loaded = await store.get("a1")
    assert loaded == record
    assert loaded.runbook.raw_markdown == record.runbook.raw_markdown
    summary = await store.summary("a1")
    assert (summary.service_name, summary.owner, summary.source) == (
        "Estimate Service",
        "Alice Chen",
        AnalysisSource.API,
    )
    assert (summary.risk_score, summary.risk_level, summary.rto_feasible) == (
        15,
        RiskLevel.LOW,
        True,
    )
    assert (summary.ai_analysis_available, summary.execution_count) == (True, 0)


async def test_record_without_inventory(tmp_path: Path) -> None:
    store = await _store(tmp_path / "h.db")
    await store.save(make_record(with_inventory=False))
    loaded = await store.get("a1")
    assert (loaded.inventory, loaded.inventory_label) == (None, None)


async def test_duplicates_and_unknown_ids(tmp_path: Path) -> None:
    store = await _store(tmp_path / "h.db")
    await store.save(make_record())
    with pytest.raises(ConflictError):
        await store.save(make_record())
    with pytest.raises(NotFoundError):
        await store.get("nope")
    with pytest.raises(NotFoundError):
        await store.summary("nope")
    with pytest.raises(NotFoundError):
        await store.delete("nope")


async def test_list_filters_and_pages_newest_first(tmp_path: Path) -> None:
    store = await _store(tmp_path / "h.db")
    await store.save(make_record("a1", minutes=1))
    await store.save(make_record("a2", minutes=2, service="Billing", risk_score=90))
    await store.save(make_record("a3", minutes=3))
    ids = [s.id for s in await store.list_page(AnalysisQuery())]
    assert ids == ["a3", "a2", "a1"]
    page = await store.list_page(AnalysisQuery(limit=2))
    assert [s.id for s in page] == ["a3", "a2"]
    rest = await store.list_page(AnalysisQuery(limit=2, before=page[-1].completed_at))
    assert [s.id for s in rest] == ["a1"]
    billing = await store.list_page(AnalysisQuery(service="Billing"))
    assert [s.id for s in billing] == ["a2"]
    critical = await store.list_page(AnalysisQuery(risk_level=RiskLevel.CRITICAL))
    assert [s.id for s in critical] == ["a2"]


async def test_executions_are_counted_and_block_deletion(tmp_path: Path) -> None:
    path = tmp_path / "h.db"
    store = await _store(path)
    await store.save(make_record("a1"))
    await store.save(make_record("a2", minutes=1))
    await store_execution(path, "exec-1", "a1")
    await store_execution(path, "exec-2", "not-stored")  # link left empty, no FK error
    assert (await store.summary("a1")).execution_count == 1
    with pytest.raises(ConflictError) as info:
        await store.delete("a1")
    assert info.value.details == {"executions": 1}
    await store.delete("a2")
    with pytest.raises(NotFoundError):
        await store.get("a2")
    with connect(path) as conn:
        links = dict(conn.execute("SELECT id, analysis_id FROM executions").fetchall())
    assert links == {"exec-1": "a1", "exec-2": None}


async def test_prune_keeps_recent_and_executed_analyses(tmp_path: Path) -> None:
    path = tmp_path / "h.db"
    store = await _store(path)
    for number, minutes in enumerate((0, 10, 60), start=1):
        await store.save(make_record(f"a{number}", minutes=minutes))
    await store_execution(path, "exec-1", "a1")
    removed = await store.prune(T0.replace(minute=30))
    assert removed == 1
    assert [s.id for s in await store.list_page(AnalysisQuery())] == ["a3", "a1"]


async def test_corrupt_rows_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "h.db"
    store = await _store(path)
    await store.save(make_record())
    with connect(path) as conn, conn:
        conn.execute("UPDATE analyses SET report_json = '{}'")
    with pytest.raises(ValidationError):
        await store.get("a1")
