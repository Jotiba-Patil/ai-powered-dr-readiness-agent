"""Connections to the shared SQLite file (stdlib `sqlite3`, ADR 0004 and 0007).

Stores open one short-lived connection per operation (foreign keys on, busy
timeout), so no connection is shared between threads. `open_database()` runs
once per store at startup: WAL mode plus any pending migrations.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from dr_agent.storage.migrations import migrate

BUSY_TIMEOUT_MS = 5000


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        yield conn
    finally:
        conn.close()


def open_database(path: Path) -> None:
    """Create or upgrade the schema; raises `ConfigError` for a newer database."""
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        migrate(conn)


def timestamp(value: datetime) -> str:
    """UTC ISO 8601 with a fixed width, so stored timestamps sort as text."""
    return value.astimezone(UTC).isoformat(timespec="microseconds")
