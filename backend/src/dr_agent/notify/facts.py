"""What a scheduled run's email may say: facts computed by code only (ADR 0011).

`EmailFacts` is built from the report's numbers and enums plus the schedule's
own settings. No runbook text and no LLM text goes in: no summary, gap
descriptions, suggestions or reasoning. The one runbook-derived string is the
service name, reduced to a plain identifier (letters, digits, `.`, `_`, `-`).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DRReadinessReport, RiskLevel, Severity

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_ERRORS = {
    "PATH_NOT_ALLOWED": "The runbook or inventory path is no longer allowed.",
    "NOT_FOUND": "The runbook or inventory file was not found.",
    "BAD_REQUEST": "The runbook or inventory file could not be read.",
    "PARSE_ERROR": "The runbook could not be parsed.",
    "VALIDATION_ERROR": "The inventory is not valid.",
    "CAPACITY_EXCEEDED": "The server was busy with other analyses; the next slot will try again.",
    "ANALYSIS_ERROR": "The analysis failed.",
}
_UNKNOWN_ERROR = "The analysis could not be completed."


@dataclass(frozen=True)
class ReportFacts:
    risk_score: int
    risk_level: RiskLevel
    rto_feasible: bool
    estimated_minutes: float
    stated_rto_minutes: float
    buffer_minutes: float
    gaps: dict[Severity, int]
    single_points_of_failure: int
    dependencies: dict[DependencyStatus, int]
    ai_analysis_available: bool


@dataclass(frozen=True)
class EmailFacts:
    schedule_name: str
    cadence: str
    run_at: datetime  # in the schedule's timezone
    manual: bool
    service: str
    owner: str | None  # only when the directory knew the runbook owner
    report: ReportFacts | None
    error_code: str | None = None
    link: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def error_text(self) -> str:
        return _ERRORS.get(self.error_code or "", _UNKNOWN_ERROR)


def report_facts(report: DRReadinessReport) -> ReportFacts:
    rto = report.rto_analysis
    gaps = Counter(gap.severity for gap in report.gap_analysis)
    deps = Counter(dep.actual_status for dep in report.dependency_health)
    return ReportFacts(
        risk_score=report.risk_score,
        risk_level=report.risk_level,
        rto_feasible=rto.feasible,
        estimated_minutes=rto.total_estimated_minutes,
        stated_rto_minutes=rto.stated_rto_minutes,
        buffer_minutes=rto.buffer_minutes,
        gaps={severity: gaps[severity] for severity in Severity},
        single_points_of_failure=len(report.single_points_of_failure),
        dependencies={status: deps[status] for status in DependencyStatus},
        ai_analysis_available=report.ai_analysis_available,
    )


def safe_identifier(value: str, *, fallback: str, limit: int = 60) -> str:
    cleaned = _UNSAFE.sub("-", value).strip("-.")[:limit]
    return cleaned or fallback
