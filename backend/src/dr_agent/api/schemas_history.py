"""Response models for the analysis history API (design analysis-history section 6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from dr_agent.api.schemas_execution import AuditView
from dr_agent.execution.models import Execution
from dr_agent.history.models import AnalysisSummary, Provenance
from dr_agent.models.base import CamelModel
from dr_agent.models.report import DRReadinessReport


class AnalysisPage(CamelModel):
    items: list[AnalysisSummary]
    next_before: datetime | None = Field(
        default=None, description="Pass as `before` for the next page; null on the last page"
    )


class AnalysisDetail(CamelModel):
    summary: AnalysisSummary
    report: DRReadinessReport
    provenance: Provenance
    stale: bool = Field(description="Older than HISTORY_STALE_AFTER_HOURS; health may differ now")


class StoredExecution(CamelModel):
    """A past execution of an analysis, read-only: its steps and its verified audit log."""

    execution: Execution
    audit: AuditView
