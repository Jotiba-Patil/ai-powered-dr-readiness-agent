"""History service: saving never fails an analysis, retention, staleness, linked executions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from history_support import T0, make_record, store_execution

from dr_agent.config import Settings
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.history.models import AnalysisQuery, AnalysisRecord
from dr_agent.history.service import History, open_history, provenance
from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.llm.prompts.analysis import PROMPT_VERSION


class BrokenStore(SqliteAnalysisStore):
    """Fails every write, as a full disk or a locked file would."""

    async def save(self, record: AnalysisRecord) -> None:
        raise sqlite3.OperationalError("database is locked")

    async def prune(self, completed_before: datetime) -> int:
        raise OSError("disk full")


async def _history(
    path: Path, *, retention_days: int = 0, stale_after_hours: float = 24.0
) -> History:
    return History(
        await SqliteAnalysisStore.open(path),
        SqliteExecutionStore(path),
        retention_days=retention_days,
        stale_after_hours=stale_after_hours,
        clock=lambda: T0,
    )


async def test_save_stores_and_reports_success(tmp_path: Path) -> None:
    history = await _history(tmp_path / "h.db")
    assert await history.save(make_record()) is True
    assert (await history.store.get("a1")).id == "a1"


async def test_save_failures_are_reported_not_raised(tmp_path: Path) -> None:
    history = await _history(tmp_path / "h.db")
    await history.save(make_record())
    assert await history.save(make_record()) is False  # duplicate id
    broken = History(
        BrokenStore(tmp_path / "h.db"), SqliteExecutionStore(tmp_path / "h.db"), retention_days=1
    )
    assert await broken.save(make_record("a2")) is False
    assert await broken.prune() == 0


async def test_retention_runs_after_each_save(tmp_path: Path) -> None:
    history = await _history(tmp_path / "h.db", retention_days=1)
    await history.store.save(make_record("old", minutes=-2 * 24 * 60))
    assert await history.save(make_record("new")) is True
    ids = [s.id for s in await history.store.list_page(AnalysisQuery())]
    assert ids == ["new"]


async def test_without_retention_nothing_is_pruned(tmp_path: Path) -> None:
    history = await _history(tmp_path / "h.db")
    await history.store.save(make_record("old", minutes=-365 * 24 * 60))
    assert await history.prune() == 0


async def test_staleness_uses_the_configured_hours(tmp_path: Path) -> None:
    history = await _history(tmp_path / "h.db", stale_after_hours=2)
    assert history.is_stale(T0 - timedelta(hours=3)) is True
    assert history.is_stale(T0 - timedelta(hours=1)) is False


async def test_executions_of_one_analysis(tmp_path: Path) -> None:
    path = tmp_path / "h.db"
    history = await _history(path)
    await history.save(make_record("a1"))
    await store_execution(path, "exec-1", "a1")
    await store_execution(path, "exec-2", "other")
    await store_execution(path, "exec-3", None)
    assert [e.id for e in await history.executions("a1")] == ["exec-1"]


def test_provenance_never_names_a_model_without_one() -> None:
    none = provenance(Settings(_env_file=None, llm_provider="none"))
    assert (none.llm_provider, none.llm_model, none.prompt_version) == (
        "none",
        None,
        PROMPT_VERSION,
    )
    ollama = provenance(Settings(_env_file=None, llm_provider="ollama", llm_model="qwen"))
    assert (ollama.llm_provider, ollama.llm_model) == ("ollama", "qwen")


async def test_open_history_follows_the_settings(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    off = Settings(_env_file=None, history_enabled=False, db_path=str(path))
    assert await open_history(off) is None
    assert not path.exists()
    on = Settings(_env_file=None, db_path=str(path), history_retention_days=1)
    history = await open_history(on, clock=lambda: T0)
    assert history is not None
    assert path.exists()
