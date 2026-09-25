"""SQLite `AnalysisStore` in the shared database file (ADR 0007).

Same pattern as the execution store: stdlib `sqlite3` run through
`asyncio.to_thread`, one short-lived connection per operation.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from dr_agent.history.models import AnalysisQuery, AnalysisRecord, AnalysisSummary
from dr_agent.history.sqlite_rows import (
    COUNT_EXECUTIONS,
    DELETE_ANALYSIS,
    INSERT_ANALYSIS,
    PRUNE,
    SELECT_RECORD,
    SELECT_SUMMARY,
    page_sql,
    record_from_row,
    record_row,
    summary_from_row,
)
from dr_agent.storage.sqlite import connect, open_database, timestamp
from dr_agent.utils.errors import ConflictError, NotFoundError


class SqliteAnalysisStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    async def open(cls, path: Path) -> SqliteAnalysisStore:
        await asyncio.to_thread(open_database, path)
        return cls(path)

    async def save(self, record: AnalysisRecord) -> None:
        await asyncio.to_thread(self._save, record)

    async def get(self, analysis_id: str) -> AnalysisRecord:
        return await asyncio.to_thread(self._get, analysis_id)

    async def summary(self, analysis_id: str) -> AnalysisSummary:
        return await asyncio.to_thread(self._summary, analysis_id)

    async def list_page(self, query: AnalysisQuery) -> list[AnalysisSummary]:
        return await asyncio.to_thread(self._list, query)

    async def delete(self, analysis_id: str) -> None:
        await asyncio.to_thread(self._delete, analysis_id)

    async def prune(self, completed_before: datetime) -> int:
        return await asyncio.to_thread(self._prune, completed_before)

    def _save(self, record: AnalysisRecord) -> None:
        try:
            with connect(self._path) as conn, conn:
                conn.execute(INSERT_ANALYSIS, record_row(record))
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"analysis {record.id} is already stored") from exc

    def _get(self, analysis_id: str) -> AnalysisRecord:
        with connect(self._path) as conn:
            row = conn.execute(SELECT_RECORD, (analysis_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"analysis {analysis_id} not found")
        return record_from_row(row)

    def _summary(self, analysis_id: str) -> AnalysisSummary:
        with connect(self._path) as conn:
            row = conn.execute(SELECT_SUMMARY, (analysis_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"analysis {analysis_id} not found")
        return summary_from_row(row)

    def _list(self, query: AnalysisQuery) -> list[AnalysisSummary]:
        sql, params = page_sql(query)
        with connect(self._path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [summary_from_row(row) for row in rows]

    def _delete(self, analysis_id: str) -> None:
        with connect(self._path) as conn, conn:
            executions = int(conn.execute(COUNT_EXECUTIONS, (analysis_id,)).fetchone()[0])
            if executions:
                raise ConflictError(
                    "an analysis with executions cannot be deleted",
                    details={"executions": executions},
                )
            if conn.execute(DELETE_ANALYSIS, (analysis_id,)).rowcount == 0:
                raise NotFoundError(f"analysis {analysis_id} not found")

    def _prune(self, completed_before: datetime) -> int:
        with connect(self._path) as conn, conn:
            return int(conn.execute(PRUNE, (timestamp(completed_before),)).rowcount)
