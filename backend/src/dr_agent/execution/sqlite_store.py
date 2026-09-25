"""SQLite `ExecutionStore` (stdlib `sqlite3` via `asyncio.to_thread`, ADR 0004).

One short-lived connection per operation through `storage/sqlite.py`, so no
connection is shared between threads. Each save is one transaction that also
checks the new audit events continue the stored chain.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dr_agent.execution.audit import AuditEvent
from dr_agent.execution.models import Execution
from dr_agent.execution.sqlite_schema import (
    DELETE_PROJECTIONS,
    EVENT_COLUMNS,
    INSERT_APPROVAL,
    INSERT_CALL,
    INSERT_EVENT,
    INSERT_EXECUTION,
    INSERT_STEP,
    SELECT_EVENTS,
    event_row,
    execution_row,
    projections,
)
from dr_agent.storage.sqlite import connect, open_database
from dr_agent.utils.errors import ConflictError, NotFoundError


class SqliteExecutionStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    async def open(cls, path: Path) -> SqliteExecutionStore:
        store = cls(path)
        await asyncio.to_thread(store._create_schema)
        return store

    async def create(self, execution: Execution, events: list[AuditEvent]) -> None:
        await asyncio.to_thread(self._write, execution, events, True)

    async def save(self, execution: Execution, events: list[AuditEvent]) -> None:
        await asyncio.to_thread(self._write, execution, events, False)

    async def get(self, execution_id: str) -> Execution:
        return await asyncio.to_thread(self._get, execution_id)

    async def list_all(self) -> list[Execution]:
        return await asyncio.to_thread(self._list)

    async def audit(self, execution_id: str) -> list[AuditEvent]:
        return await asyncio.to_thread(self._audit, execution_id)

    def _create_schema(self) -> None:
        open_database(self._path)

    def _write(self, execution: Execution, events: list[AuditEvent], new: bool) -> None:
        with connect(self._path) as conn, conn:  # the inner `conn` is the transaction
            row = conn.execute(
                "SELECT audit_seq FROM executions WHERE id = ?", (execution.id,)
            ).fetchone()
            if new and row is not None:
                raise ConflictError(f"execution {execution.id} already exists")
            if not new and row is None:
                raise NotFoundError(f"execution {execution.id} not found")
            stored_seq = 0 if row is None else int(row[0])
            if events and events[0].seq != stored_seq + 1:
                raise ConflictError(
                    "execution changed concurrently; reload and try again",
                    details={"storedSeq": stored_seq, "firstNewSeq": events[0].seq},
                )
            conn.execute(INSERT_EXECUTION, execution_row(execution))
            for statement in DELETE_PROJECTIONS:
                conn.execute(statement, (execution.id,))
            steps, calls, approvals = projections(execution)
            conn.executemany(INSERT_STEP, steps)
            conn.executemany(INSERT_CALL, calls)
            conn.executemany(INSERT_APPROVAL, approvals)
            conn.executemany(INSERT_EVENT, [event_row(event) for event in events])

    def _get(self, execution_id: str) -> Execution:
        with connect(self._path) as conn:
            row = conn.execute(
                "SELECT plan_json FROM executions WHERE id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"execution {execution_id} not found")
        return Execution.model_validate_json(row[0])

    def _list(self) -> list[Execution]:
        with connect(self._path) as conn:
            rows = conn.execute(
                "SELECT plan_json FROM executions ORDER BY created_at DESC, id"
            ).fetchall()
        return [Execution.model_validate_json(row[0]) for row in rows]

    def _audit(self, execution_id: str) -> list[AuditEvent]:
        self._get(execution_id)  # NotFoundError for an unknown id
        with connect(self._path) as conn:
            rows = conn.execute(SELECT_EVENTS, (execution_id,)).fetchall()
        events: list[AuditEvent] = []
        for row in rows:
            data = dict(zip(EVENT_COLUMNS, row, strict=True))
            data["payload"] = json.loads(row[4])
            events.append(AuditEvent.model_validate(data))
        return events
