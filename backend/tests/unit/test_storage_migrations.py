"""Numbered migrations of the shared SQLite file (design analysis-history 4.3)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dr_agent.storage import migrations
from dr_agent.storage.migrations import LATEST_VERSION, MIGRATIONS, migrate, schema_version
from dr_agent.storage.sqlite import connect, open_database, timestamp
from dr_agent.utils.errors import ConfigError

_V1_EXECUTION = (
    "INSERT INTO executions VALUES "
    "('old', 'COMPLETED', 'live', 'x.md', 'abc', 'Olivia', 't1', 't2', 3, 'h', '{}')"
)


def _tables(path: Path) -> set[str]:
    with connect(path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def _version_1_file(path: Path) -> None:
    """A database as Phases 9-11 left it: execution tables, version 1, one execution."""
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version VALUES (1)")
        for statement in MIGRATIONS[0]:
            conn.execute(statement)
        conn.execute(_V1_EXECUTION)


def test_fresh_file_gets_every_migration(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    open_database(path)
    assert {"executions", "audit_events", "analyses", "schema_version"} <= _tables(path)
    with connect(path) as conn:
        assert schema_version(conn) == LATEST_VERSION == 2
        columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
    assert "analysis_id" in columns


def test_version_1_file_keeps_its_executions(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    _version_1_file(path)
    open_database(path)
    open_database(path)  # idempotent
    with connect(path) as conn:
        assert schema_version(conn) == LATEST_VERSION
        rows = conn.execute("SELECT id, audit_seq, analysis_id FROM executions").fetchall()
    assert rows == [("old", 3, None)]


def test_newer_database_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "new.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version VALUES (99)")
    with pytest.raises(ConfigError) as info:
        open_database(path)
    assert info.value.details == {"databaseVersion": 99, "supportedVersion": LATEST_VERSION}


def test_failed_migration_is_rolled_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "db.sqlite"
    broken = (MIGRATIONS[0], ("CREATE TABLE half_done (x INTEGER)", "NOT VALID SQL"))
    monkeypatch.setattr(migrations, "MIGRATIONS", broken)
    with connect(path) as conn:
        with pytest.raises(sqlite3.OperationalError):
            migrate(conn)
        assert schema_version(conn) == 1
    assert "half_done" not in _tables(path)


def test_timestamps_have_a_fixed_width_in_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert timestamp(datetime(2026, 9, 25, 12, 0, tzinfo=plus_two)) == (
        "2026-09-25T10:00:00.000000+00:00"
    )
