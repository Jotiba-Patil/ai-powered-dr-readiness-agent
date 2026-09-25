# 0004. Durable execution state in SQLite

- Status: Accepted (2026-09-24); partly superseded by [0007](0007-persist-analyses.md) (analyses are stored) and [0008](0008-store-raw-runbook.md) (runbook text is stored with the analysis)
- Date: 2026-09-23
- Related: [design](../design/runbook-execution.md) section 7

## Context

Analysis jobs live in memory (`api/jobs.py`); losing them on restart is harmless. An execution is different: a restart in the middle of a failover must not lose approvals or the audit trail, and must not re-run a call whose outcome is unknown. We want durability without adding a database server to the stack.

## Decision

- Add an `ExecutionStore` protocol in `execution/store.py` and a SQLite implementation in `execution/sqlite_store.py`, using the standard-library `sqlite3` module run through `asyncio.to_thread` (no new dependency).
- Tables: `executions`, `step_runs`, `tool_calls`, `approvals`, `audit_events` (design section 7). Schema is created at startup with a `schema_version` table for later migrations.
- Each state change and its audit event are written in **one transaction**. WAL mode, foreign keys on, a busy timeout set.
- The runbook text is not stored, only its SHA-256 and the parsed plan.
- **Restart recovery:** at startup every step in `RUNNING` becomes `UNKNOWN` and its execution `PAUSED`, with an audit event. Nothing is resumed or retried automatically.
- `EXECUTION_DB_PATH` sets the file. In Docker it lives on a named volume, because container root filesystems are read-only.
- Tests use a database file in `tmp_path`.

## Consequences

- Executions and audit trails survive restarts; the audit log can be exported and verified at any time.
- One API instance per database file. Horizontal scaling would need a different store (for example PostgreSQL) behind the same protocol.
- A small amount of schema and migration code to maintain.
- Analysis jobs stay in memory; only executions are persisted.

## Alternatives considered

- **Keep executions in memory like jobs.** Unacceptable: a restart could lose approvals and hide half-finished actions.
- **PostgreSQL or Redis.** Durable and scalable, but an extra service for a single-instance PoC.
- **JSON files per execution.** No transactions, so a state change and its audit event could diverge after a crash.
- **`aiosqlite`.** Works, but adds a dependency for what `asyncio.to_thread` already gives us.
