"""`AnalysisStore` protocol: stored analyses, linked to executions (ADR 0007)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from dr_agent.history.models import AnalysisQuery, AnalysisRecord, AnalysisSummary


class AnalysisStore(Protocol):
    async def save(self, record: AnalysisRecord) -> None:
        """Raises `ConflictError` if the id is already stored."""
        ...

    async def get(self, analysis_id: str) -> AnalysisRecord:
        """Raises `NotFoundError` for an unknown id."""
        ...

    async def summary(self, analysis_id: str) -> AnalysisSummary:
        """Raises `NotFoundError` for an unknown id."""
        ...

    async def list_page(self, query: AnalysisQuery) -> list[AnalysisSummary]:
        """Newest first (by completion time)."""
        ...

    async def delete(self, analysis_id: str) -> None:
        """`NotFoundError` for an unknown id, `ConflictError` if executions refer to it."""
        ...

    async def prune(self, completed_before: datetime) -> int:
        """Delete older analyses that have no executions; returns how many."""
        ...
