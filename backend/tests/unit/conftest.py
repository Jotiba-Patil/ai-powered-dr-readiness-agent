"""Shared fixtures for formatter tests: one fully-populated DRReadinessReport."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dr_agent import __version__
from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import (
    DependencyHealth,
    DRReadinessReport,
    ExecutionPhase,
    Gap,
    GapType,
    ReportMeta,
    RtoAnalysis,
    ServiceSummary,
    Severity,
    SinglePointOfFailure,
    Suggestion,
)


@pytest.fixture
def sample_report() -> DRReadinessReport:
    return DRReadinessReport(
        meta=ReportMeta(
            analyzed_at=datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC),
            runbook_file="estimate-service.md",
            inventory_file="healthy.json",
            agent_version=__version__,
            analysis_time_ms=123.4,
        ),
        service_summary=ServiceSummary(
            name="Estimate Service", owner="Alice Chen", stated_rto=60, stated_rpo=15
        ),
        risk_score=42,
        rto_analysis=RtoAnalysis(
            feasible=True,
            total_estimated_minutes=55,
            stated_rto_minutes=60,
            buffer_minutes=5,
            bottleneck_steps=[],
        ),
        dependency_health=[
            DependencyHealth(
                name="estimate-postgres",
                actual_status=DependencyStatus.UP,
                impact="referenced by step(s) 3",
            ),
            DependencyHealth(
                name="rates-kafka-topic",
                actual_status=DependencyStatus.NOT_IN_INVENTORY,
                impact="not directly referenced by any recovery step",
            ),
        ],
        single_points_of_failure=[
            SinglePointOfFailure(
                description="Only Alice can approve the traffic flip",
                affected_steps=[5],
                mitigation_suggestion="Cross-train a second engineer",
            )
        ],
        gap_analysis=[
            Gap(
                type=GapType.NO_VALIDATION,
                description="Step 1 has no validation command",
                severity=Severity.MEDIUM,
                recommendation="Add a validation command",
            )
        ],
        execution_plan=[
            ExecutionPhase(phase=1, steps=[1, 2], estimated_minutes=15, gate="none: initial phase"),
            ExecutionPhase(phase=2, steps=[3], estimated_minutes=10, gate="step(s) 1 complete"),
        ],
        suggestions=[
            Suggestion(priority=1, title="Add a rollback rehearsal", detail="Test quarterly")
        ],
        summary="Estimate Service is in good shape with one ownership risk to address.",
    )
