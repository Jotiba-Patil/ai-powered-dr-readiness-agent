"""The knowledge base the API and CLI inject into `analyze_runbook()` (ADR 0009).

Reading history never fails an analysis: a storage error is logged and the
analysis goes on without history, exactly as if there were none.
"""

from __future__ import annotations

import sqlite3

from dr_agent.config import Settings
from dr_agent.knowledge.facts import build_history, for_runbook
from dr_agent.knowledge.source import KnowledgeSource, SqliteKnowledgeSource
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.runbook import Runbook
from dr_agent.utils.errors import AppError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.knowledge")


class KnowledgeBase:
    def __init__(
        self,
        source: KnowledgeSource,
        *,
        max_runs: int = 10,
        max_analyses: int = 20,
        in_prompt: bool = True,
    ) -> None:
        self._source = source
        self._max_runs = max_runs
        self._max_analyses = max_analyses
        self.in_prompt = in_prompt

    async def service_history(self, service: str) -> ServiceHistory:
        """Everything stored about one service (steps keyed by fingerprint)."""
        return build_history(
            service,
            await self._source.analyses(service, self._max_analyses),
            await self._source.live_runs(service, self._max_runs),
            await self._source.dry_run_count(service),
        )

    async def insights_for(self, runbook: Runbook) -> ServiceHistory | None:
        """History matched to this runbook's steps; None when there is none (or it failed)."""
        try:
            history = await self.service_history(runbook.service_name)
        except (AppError, sqlite3.Error, OSError, KeyError, ValueError) as exc:
            _log.error("history_unavailable", error_type=type(exc).__name__)
            return None
        return None if history.empty else for_runbook(history, runbook)


def open_knowledge(settings: Settings) -> KnowledgeBase | None:
    """None unless both `HISTORY_ENABLED` and `KNOWLEDGE_ENABLED` are true."""
    if not (settings.history_enabled and settings.knowledge_enabled):
        return None
    return KnowledgeBase(
        SqliteKnowledgeSource(settings.database_path),
        max_runs=settings.knowledge_max_runs,
        max_analyses=settings.knowledge_max_analyses,
        in_prompt=settings.knowledge_in_prompt,
    )
