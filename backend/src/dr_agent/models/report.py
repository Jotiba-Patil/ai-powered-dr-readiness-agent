"""DRReadinessReport and its parts. `riskLevel` is always derived from `riskScore`."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, computed_field, model_validator

from dr_agent.models.base import CamelModel
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.inventory import DependencyStatus


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GapType(StrEnum):
    MISSING_STEP = "MISSING_STEP"
    VAGUE_INSTRUCTION = "VAGUE_INSTRUCTION"
    NO_VALIDATION = "NO_VALIDATION"
    MISSING_ROLLBACK = "MISSING_ROLLBACK"
    UNVERIFIED_DEPENDENCY = "UNVERIFIED_DEPENDENCY"
    OWNER_AMBIGUITY = "OWNER_AMBIGUITY"
    HISTORICAL = "HISTORICAL"  # found in past live runs or analyses (ADR 0009)


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


CRITICAL_THRESHOLD = 80  # CLI exits with code 2 above this score


def risk_level_from_score(score: int) -> RiskLevel:
    """0-25 LOW, 26-50 MEDIUM, 51-80 HIGH, 81-100 CRITICAL."""
    if score <= 25:
        return RiskLevel.LOW
    if score <= 50:
        return RiskLevel.MEDIUM
    if score <= CRITICAL_THRESHOLD:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


class ReportMeta(CamelModel):
    analyzed_at: datetime
    runbook_file: str
    inventory_file: str
    agent_version: str
    analysis_time_ms: float = Field(ge=0)


class ServiceSummary(CamelModel):
    name: str
    owner: str
    stated_rto: float = Field(alias="statedRTO", gt=0, description="Minutes")
    stated_rpo: float = Field(alias="statedRPO", gt=0, description="Minutes")


class RtoAnalysis(CamelModel):
    feasible: bool
    total_estimated_minutes: float = Field(ge=0)
    stated_rto_minutes: float = Field(gt=0)
    buffer_minutes: float = Field(description="Stated RTO minus estimated total; may be negative")
    bottleneck_steps: list[int] = Field(default_factory=list)


class DependencyHealth(CamelModel):
    name: str
    runbook_assumes: Literal["available"] = "available"
    actual_status: DependencyStatus
    impact: str = Field(description="Which steps are affected")


class SinglePointOfFailure(CamelModel):
    description: str
    affected_steps: list[int] = Field(default_factory=list)
    mitigation_suggestion: str


class Gap(CamelModel):
    type: GapType
    description: str
    severity: Severity
    recommendation: str


class ExecutionPhase(CamelModel):
    phase: int = Field(ge=1)
    steps: list[int] = Field(description="Steps that can run in parallel")
    estimated_minutes: float = Field(ge=0)
    gate: str = Field(description="What must be true before proceeding")


class Suggestion(CamelModel):
    priority: int = Field(ge=1, le=5)
    title: str
    detail: str


class DRReadinessReport(CamelModel):
    meta: ReportMeta
    service_summary: ServiceSummary
    risk_score: int = Field(ge=0, le=100, strict=True)  # strict: reject true/4.5/"80" from LLMs
    rto_analysis: RtoAnalysis
    dependency_health: list[DependencyHealth] = Field(default_factory=list)
    single_points_of_failure: list[SinglePointOfFailure] = Field(default_factory=list)
    gap_analysis: list[Gap] = Field(default_factory=list)
    execution_plan: list[ExecutionPhase] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    summary: str
    # Graceful degradation: set when the LLM was unavailable and only rule-based results exist.
    ai_analysis_available: bool = True
    ai_note: str | None = None
    # Knowledge base (Phase 14): left out of the JSON entirely when there is no history.
    historical_insights: ServiceHistory | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @computed_field  # type: ignore[prop-decorator]  # pydantic mypy plugin limitation
    @property
    def risk_level(self) -> RiskLevel:
        return risk_level_from_score(self.risk_score)

    @model_validator(mode="before")
    @classmethod
    def _accept_derived_level(cls, data: object) -> object:
        """Allow round-tripping serialized reports, but reject an inconsistent riskLevel."""
        if not isinstance(data, dict):
            return data
        given = data.get("riskLevel", data.get("risk_level"))
        rest = {k: v for k, v in data.items() if k not in {"riskLevel", "risk_level"}}
        score = rest.get("riskScore", rest.get("risk_score"))
        if given is not None and isinstance(score, int) and not isinstance(score, bool):
            expected = risk_level_from_score(score) if 0 <= score <= 100 else None
            if expected is not None and str(given) != expected.value:
                raise ValueError(f"riskLevel {given!r} does not match riskScore {score}")
        return rest

    @model_validator(mode="after")
    def _check_ai_note(self) -> Self:
        if not self.ai_analysis_available and not self.ai_note:
            raise ValueError("aiNote is required when aiAnalysisAvailable is false")
        return self
