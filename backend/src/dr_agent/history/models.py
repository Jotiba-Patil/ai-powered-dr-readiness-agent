"""A stored analysis and its summary (design analysis-history section 4.1).

`AnalysisRecord` is everything needed to reopen or re-execute an analysis:
the report, the parsed runbook (with its raw Markdown, ADR 0008), the
inventory it was checked against and how the report was produced.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from dr_agent.models.base import CamelModel
from dr_agent.models.inventory import SystemInventory
from dr_agent.models.report import DRReadinessReport, RiskLevel
from dr_agent.models.runbook import Runbook

AnalysisId = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
MAX_PAGE = 100


class AnalysisSource(StrEnum):
    API = "api"
    CLI = "cli"


class Provenance(CamelModel):
    """How a report was produced; never the API key or base URL."""

    llm_provider: str
    llm_model: str | None = None
    prompt_version: str
    agent_version: str


class AnalysisRecord(CamelModel):
    id: str = AnalysisId
    source: AnalysisSource
    created_at: datetime
    completed_at: datetime
    runbook_label: str
    runbook: Runbook
    inventory_label: str | None = None
    inventory: SystemInventory | None = None
    report: DRReadinessReport
    provenance: Provenance


class AnalysisSummary(CamelModel):
    id: str
    service_name: str
    owner: str
    source: AnalysisSource
    created_at: datetime
    completed_at: datetime
    runbook_label: str
    inventory_label: str | None
    risk_score: int
    risk_level: RiskLevel
    rto_feasible: bool
    ai_analysis_available: bool
    execution_count: int = Field(ge=0)


class AnalysisQuery(CamelModel):
    """Newest first; `before` is the `completedAt` of the last item of the previous page."""

    service: str | None = Field(default=None, min_length=1, max_length=200)
    risk_level: RiskLevel | None = None
    limit: int = Field(default=20, ge=1, le=MAX_PAGE)
    before: datetime | None = None
