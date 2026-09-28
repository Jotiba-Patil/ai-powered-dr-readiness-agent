"""SQLite `ScheduleStore` in the shared database file (ADR 0010).

Same pattern as the other stores: stdlib `sqlite3` through `asyncio.to_thread`,
one short-lived connection per operation. Claiming runs in one `BEGIN IMMEDIATE`
transaction, and a unique index on (schedule, slot, trigger) backs it up, so a
slot is never started twice.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from dr_agent.scheduling import sqlite_rows as sql
from dr_agent.scheduling.models import RunTrigger, Schedule, SchedulerState, ScheduleRun
from dr_agent.scheduling.sqlite_claim import claim_due, restart_all
from dr_agent.scheduling.store import IdFactory, NextSlot
from dr_agent.storage.sqlite import connect, open_database, timestamp
from dr_agent.utils.errors import ConflictError, NotFoundError


class SqliteScheduleStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    async def open(cls, path: Path) -> SqliteScheduleStore:
        await asyncio.to_thread(open_database, path)
        return cls(path)

    async def create(self, schedule: Schedule) -> None:
        await asyncio.to_thread(self._write, sql.INSERT_SCHEDULE, sql.schedule_row(schedule))

    async def get(self, schedule_id: str) -> Schedule:
        return await asyncio.to_thread(self._get, schedule_id)

    async def list_all(self) -> list[Schedule]:
        rows = await asyncio.to_thread(self._rows, sql.SELECT_SCHEDULES, ())
        return [sql.schedule_from_row(row) for row in rows]

    async def update(self, schedule: Schedule) -> None:
        row = sql.schedule_row(schedule)
        changed = await asyncio.to_thread(self._write, sql.UPDATE_SCHEDULE, (*row[1:], row[0]))
        if not changed:
            raise NotFoundError(f"schedule {schedule.id} not found")

    async def delete(self, schedule_id: str) -> None:
        if not await asyncio.to_thread(self._write, sql.DELETE_SCHEDULE, (schedule_id,)):
            raise NotFoundError(f"schedule {schedule_id} not found")

    async def claim_due(
        self, now: datetime, next_slot: NextSlot, new_id: IdFactory
    ) -> list[ScheduleRun]:
        return await asyncio.to_thread(
            self._in_transaction, lambda conn: claim_due(conn, now, next_slot, new_id)
        )

    async def start_manual(self, schedule_id: str, now: datetime, run_id: str) -> ScheduleRun:
        return await asyncio.to_thread(self._start_manual, schedule_id, now, run_id)

    async def save_run(self, run: ScheduleRun) -> None:
        await asyncio.to_thread(self._write, sql.UPDATE_RUN, sql.run_row(run))

    async def get_run(self, run_id: str) -> ScheduleRun:
        rows = await asyncio.to_thread(self._rows, sql.SELECT_RUN, (run_id,))
        if not rows:
            raise NotFoundError(f"schedule run {run_id} not found")
        return sql.run_from_row(rows[0])

    async def list_runs(
        self, schedule_id: str, *, limit: int, before: datetime | None = None
    ) -> list[ScheduleRun]:
        params: tuple[object, ...] = (schedule_id,)
        params += (timestamp(before), limit) if before else (limit,)
        rows = await asyncio.to_thread(self._rows, sql.runs_page_sql(before), params)
        return [sql.run_from_row(row) for row in rows]

    async def latest_runs(self) -> dict[str, ScheduleRun]:
        rows = await asyncio.to_thread(self._rows, sql.SELECT_LATEST_RUNS, ())
        runs = (sql.run_from_row(row) for row in rows)
        return {run.schedule_id: run for run in runs}

    async def fail_interrupted(self, now: datetime) -> int:
        return await asyncio.to_thread(self._write, sql.FAIL_INTERRUPTED, (timestamp(now),))

    async def get_state(self) -> SchedulerState:
        rows = await asyncio.to_thread(self._rows, sql.SELECT_STATE, ())
        return sql.state_from_row(rows[0])

    async def pause_all(self, state: SchedulerState) -> None:
        await asyncio.to_thread(self._write, sql.UPDATE_STATE, sql.state_row(state))

    async def resume_all(self, now: datetime, next_slot: NextSlot) -> None:
        await asyncio.to_thread(
            self._in_transaction, lambda conn: restart_all(conn, now, next_slot)
        )

    def _write(self, statement: str, params: tuple[object, ...]) -> int:
        with connect(self._path) as conn, conn:
            return conn.execute(statement, params).rowcount

    def _rows(self, statement: str, params: tuple[object, ...]) -> list[sql.Row]:
        with connect(self._path) as conn:
            return [tuple(row) for row in conn.execute(statement, params).fetchall()]

    def _get(self, schedule_id: str) -> Schedule:
        rows = self._rows(sql.SELECT_SCHEDULE, (schedule_id,))
        if not rows:
            raise NotFoundError(f"schedule {schedule_id} not found")
        return sql.schedule_from_row(rows[0])

    def _start_manual(self, schedule_id: str, now: datetime, run_id: str) -> ScheduleRun:
        self._get(schedule_id)
        run = ScheduleRun(
            id=run_id,
            schedule_id=schedule_id,
            slot_at=now,
            trigger=RunTrigger.MANUAL,
            started_at=now,
        )
        with connect(self._path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if conn.execute(sql.RUNNING_OF, (schedule_id,)).fetchone():
                    raise ConflictError("a run of this schedule is still going")
                conn.execute(sql.INSERT_RUN, sql.run_row(run))
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise ConflictError("a run for this moment already exists") from exc
            except (sqlite3.Error, ConflictError):
                conn.execute("ROLLBACK")
                raise
        return run

    def _in_transaction[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        with connect(self._path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = work(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return result
