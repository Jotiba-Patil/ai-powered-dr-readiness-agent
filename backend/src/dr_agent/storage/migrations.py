"""Numbered schema migrations for the shared SQLite file (design analysis-history 4.3).

`schema_version` holds the highest applied migration. Each pending migration
runs in its own explicit transaction (Python's `sqlite3` does not wrap DDL in
one by itself). A database newer than this code is refused, never downgraded.
"""

from __future__ import annotations

import sqlite3

from dr_agent.utils.errors import ConfigError

# 1: executions (Phase 9, ADR 0004). Written with IF NOT EXISTS because
# databases from before numbered migrations already have these tables.
_EXECUTIONS = (
    """CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY, state TEXT NOT NULL, mode TEXT NOT NULL,
    runbook_label TEXT NOT NULL, runbook_sha256 TEXT NOT NULL, started_by TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    audit_seq INTEGER NOT NULL, audit_head TEXT NOT NULL, plan_json TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS step_runs (
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL, phase INTEGER NOT NULL, state TEXT NOT NULL,
    attempt INTEGER NOT NULL, summary TEXT,
    PRIMARY KEY (execution_id, step_number))""",
    """CREATE TABLE IF NOT EXISTS tool_calls (
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL, kind TEXT NOT NULL, server TEXT NOT NULL, tool TEXT NOT NULL,
    arguments_json TEXT NOT NULL, source TEXT NOT NULL, risk_class TEXT, call_hash TEXT NOT NULL,
    result_json TEXT, error TEXT, started_at TEXT, finished_at TEXT,
    PRIMARY KEY (execution_id, step_number, kind))""",
    """CREATE TABLE IF NOT EXISTS approvals (
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL, kind TEXT NOT NULL, approver TEXT NOT NULL, comment TEXT,
    call_hash TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS audit_events (
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL, type TEXT NOT NULL, actor TEXT NOT NULL, payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (execution_id, seq))""",
)

# 2: stored analyses, linked from executions (Phase 13, ADR 0007 and 0008).
_ANALYSES = (
    """CREATE TABLE analyses (
    id TEXT PRIMARY KEY, service_name TEXT NOT NULL, owner TEXT NOT NULL,
    created_at TEXT NOT NULL, completed_at TEXT NOT NULL, source TEXT NOT NULL,
    runbook_label TEXT NOT NULL, runbook_sha256 TEXT NOT NULL, runbook_markdown TEXT NOT NULL,
    inventory_label TEXT, inventory_json TEXT,
    risk_score INTEGER NOT NULL, risk_level TEXT NOT NULL, rto_feasible INTEGER NOT NULL,
    ai_analysis_available INTEGER NOT NULL, llm_provider TEXT NOT NULL, llm_model TEXT,
    prompt_version TEXT NOT NULL, agent_version TEXT NOT NULL,
    runbook_json TEXT NOT NULL, report_json TEXT NOT NULL)""",
    "CREATE INDEX analyses_by_service ON analyses (service_name, completed_at)",
    "CREATE INDEX analyses_by_time ON analyses (completed_at, id)",
    "ALTER TABLE executions ADD COLUMN analysis_id TEXT REFERENCES analyses(id) ON DELETE RESTRICT",
    "CREATE INDEX executions_by_analysis ON executions (analysis_id)",
)

MIGRATIONS: tuple[tuple[str, ...], ...] = (_EXECUTIONS, _ANALYSES)
LATEST_VERSION = len(MIGRATIONS)


def schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations in order; returns the resulting version."""
    version = schema_version(conn)
    if version > LATEST_VERSION:
        raise ConfigError(
            "the database was created by a newer dr-agent; refusing to use it",
            details={"databaseVersion": version, "supportedVersion": LATEST_VERSION},
        )
    for number in range(version + 1, LATEST_VERSION + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in MIGRATIONS[number - 1]:
                conn.execute(statement)
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version VALUES (?)", (number,))
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
    return LATEST_VERSION
