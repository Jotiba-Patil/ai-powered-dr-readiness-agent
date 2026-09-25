"""Where the knowledge base reads history from: a protocol and its SQLite implementation.

Only analyses and **finished live** executions of one service are read; an
execution belongs to a service through the analysis it followed (executions
created before migration 2, or from unsaved analyses, have no link and are
left out). Same pattern as the stores: `sqlite3` through `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from dr_agent.execution.models import Execution
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.history.models import AnalysisRecord
from dr_agent.history.sqlite_rows import RECORD_COLUMNS, record_from_row
from dr_agent.knowledge.facts import PastRun
from dr_agent.storage.sqlite import connect, open_database

_ANALYSES = (  # constant column list; every value is a bound parameter
    f"SELECT {RECORD_COLUMNS} FROM analyses WHERE service_name = ? "  # noqa: S608
    "ORDER BY completed_at DESC, id DESC LIMIT ?"
)
_LIVE_RUNS = (
    "SELECT e.plan_json, a.report_json FROM executions e JOIN analyses a ON a.id = e.analysis_id "
    "WHERE a.service_name = ? AND e.mode = 'live' "
    "AND e.state IN ('COMPLETED', 'FAILED', 'ABORTED') "
    "ORDER BY e.created_at DESC, e.id DESC LIMIT ?"
)
_DRY_RUNS = (
    "SELECT COUNT(*) FROM executions e JOIN analyses a ON a.id = e.analysis_id "
    "WHERE a.service_name = ? AND e.mode = 'dry_run'"
)


class KnowledgeSource(Protocol):
    async def analyses(self, service: str, limit: int) -> list[AnalysisRecord]:
        """Newest first."""
        ...

    async def live_runs(self, service: str, limit: int) -> list[PastRun]:
        """Finished live executions, newest first."""
        ...

    async def dry_run_count(self, service: str) -> int: ...


class SqliteKnowledgeSource:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._executions = SqliteExecutionStore(path)
        self._ready = False  # schema created on first use, like the stores' open()

    async def analyses(self, service: str, limit: int) -> list[AnalysisRecord]:
        rows = await asyncio.to_thread(self._rows, _ANALYSES, (service, limit))
        return [record_from_row(row) for row in rows]

    async def live_runs(self, service: str, limit: int) -> list[PastRun]:
        rows = await asyncio.to_thread(self._rows, _LIVE_RUNS, (service, limit))
        runs: list[PastRun] = []
        for plan_json, report_json in rows:
            execution = Execution.model_validate_json(str(plan_json))
            rto = float(json.loads(str(report_json))["serviceSummary"]["statedRTO"])
            runs.append(PastRun(execution, await self._executions.audit(execution.id), rto))
        return runs

    async def dry_run_count(self, service: str) -> int:
        rows = await asyncio.to_thread(self._rows, _DRY_RUNS, (service,))
        return int(str(rows[0][0]))

    def _rows(self, sql: str, params: tuple[object, ...]) -> list[tuple[object, ...]]:
        if not self._ready:  # a brand-new database file has no tables yet
            open_database(self._path)
            self._ready = True
        with connect(self._path) as conn:
            return [tuple(row) for row in conn.execute(sql, params).fetchall()]
