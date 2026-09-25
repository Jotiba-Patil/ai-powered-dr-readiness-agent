"""Analysis history for the API and CLI: saving, retention, staleness, linked executions.

Saving never fails an analysis (design analysis-history 5.1): a storage error is
logged and reported as "not saved". Framework-free; the stores are injected
(`open_history()` builds the SQLite ones from settings).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from dr_agent import __version__
from dr_agent.config import Settings
from dr_agent.execution.audit import AuditEvent
from dr_agent.execution.models import Execution
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.execution.store import ExecutionStore
from dr_agent.history.models import AnalysisRecord, Provenance
from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.history.store import AnalysisStore
from dr_agent.llm.prompts.analysis import PROMPT_VERSION
from dr_agent.utils.errors import AppError, NotFoundError
from dr_agent.utils.logging import get_logger

Clock = Callable[[], datetime]

_log = get_logger("dr_agent.history")


class History:
    def __init__(
        self,
        store: AnalysisStore,
        executions: ExecutionStore,
        *,
        retention_days: int = 0,
        stale_after_hours: float = 24.0,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self.store = store
        self._executions = executions
        self._retention = timedelta(days=retention_days) if retention_days else None
        self._stale_after = timedelta(hours=stale_after_hours)
        self._clock = clock

    async def save(self, record: AnalysisRecord) -> bool:
        """Store the record, then apply retention; False (and logged) if it was not stored."""
        try:
            await self.store.save(record)
        except (AppError, sqlite3.Error, OSError) as exc:
            _log.error("analysis_not_saved", analysis_id=record.id, error_type=type(exc).__name__)
            return False
        _log.info("analysis_saved", analysis_id=record.id, source=record.source.value)
        await self.prune()
        return True

    async def prune(self) -> int:
        """Delete analyses past `HISTORY_RETENTION_DAYS` that have no executions."""
        if self._retention is None:
            return 0
        try:
            removed = await self.store.prune(self._clock() - self._retention)
        except (sqlite3.Error, OSError) as exc:
            _log.error("history_prune_failed", error_type=type(exc).__name__)
            return 0
        if removed:
            _log.info("history_pruned", removed=removed)
        return removed

    def is_stale(self, completed_at: datetime) -> bool:
        return self._clock() - completed_at > self._stale_after

    async def executions(self, analysis_id: str) -> list[Execution]:
        """Executions created from this analysis, newest first."""
        return [
            execution
            for execution in await self._executions.list_all()
            if execution.analysis is not None and execution.analysis.job_id == analysis_id
        ]

    async def execution(
        self, analysis_id: str, execution_id: str
    ) -> tuple[Execution, list[AuditEvent]]:
        """One execution of this analysis with its audit events (read-only history view)."""
        execution = await self._executions.get(execution_id)
        if execution.analysis is None or execution.analysis.job_id != analysis_id:
            raise NotFoundError(f"execution {execution_id} not found for analysis {analysis_id}")
        return execution, await self._executions.audit(execution_id)


def provenance(settings: Settings) -> Provenance:
    no_model = settings.llm_provider == "none"
    return Provenance(
        llm_provider=settings.llm_provider,
        llm_model=None if no_model else settings.llm_model,
        prompt_version=PROMPT_VERSION,
        agent_version=__version__,
    )


async def open_history(settings: Settings, *, clock: Clock | None = None) -> History | None:
    """The SQLite-backed history, or None with `HISTORY_ENABLED=false`."""
    if not settings.history_enabled:
        return None
    path = settings.database_path
    history = History(
        await SqliteAnalysisStore.open(path),
        SqliteExecutionStore(path),
        retention_days=settings.history_retention_days,
        stale_after_hours=settings.history_stale_after_hours,
        clock=clock or (lambda: datetime.now(UTC)),
    )
    await history.prune()
    return history
