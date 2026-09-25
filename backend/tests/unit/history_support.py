"""Shared helpers for the history tests: records built from the golden report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from exec_support import OPERATOR, drsim_catalog, drsim_policy, executable_runbook

from dr_agent import __version__
from dr_agent.core.parser import parse_runbook
from dr_agent.execution.analysis_link import analysis_ref
from dr_agent.execution.models import ExecutionMode
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.history.models import AnalysisRecord, AnalysisSource, Provenance
from dr_agent.models.inventory import SystemInventory
from dr_agent.models.report import DRReadinessReport

REPO_ROOT = Path(__file__).resolve().parents[3]
MOCK = REPO_ROOT / "mock-data"
T0 = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)
PROVENANCE = Provenance(llm_provider="none", prompt_version="analysis/1", agent_version=__version__)


def golden_report() -> DRReadinessReport:
    text = (MOCK / "expected-reports" / "estimate-service.json").read_text(encoding="utf-8")
    return DRReadinessReport.model_validate_json(text)


def make_record(
    analysis_id: str = "a1",
    *,
    minutes: int = 0,
    service: str | None = None,
    risk_score: int | None = None,
    with_inventory: bool = True,
) -> AnalysisRecord:
    runbook = parse_runbook((MOCK / "runbooks" / "estimate-service.md").read_text("utf-8"))
    if service is not None:
        runbook = runbook.model_copy(update={"service_name": service})
    report = golden_report()
    if risk_score is not None:
        report = report.model_copy(update={"risk_score": risk_score})
    inventory = SystemInventory.model_validate_json(
        (MOCK / "inventories" / "healthy.json").read_text("utf-8")
    )
    completed = T0 + timedelta(minutes=minutes)
    return AnalysisRecord(
        id=analysis_id,
        source=AnalysisSource.API,
        created_at=completed - timedelta(seconds=30),
        completed_at=completed,
        runbook_label="estimate-service.md",
        runbook=runbook,
        inventory_label="healthy.json" if with_inventory else None,
        inventory=inventory if with_inventory else None,
        report=report,
        provenance=PROVENANCE,
    )


async def store_execution(
    path: Path, execution_id: str, analysis_id: str | None, *, minutes: int = 5
) -> None:
    """A planned execution linked to `analysis_id`, written through the execution store."""
    execution, events = plan_execution(
        executable_runbook(),
        policy=drsim_policy(),
        catalog=index_catalog(drsim_catalog()),
        execution_id=execution_id,
        mode=ExecutionMode.DRY_RUN,
        started_by=OPERATOR,
        runbook_label="estimate-service.md",
        now=T0 + timedelta(minutes=minutes),
        analysis=analysis_ref(analysis_id, golden_report()) if analysis_id else None,
    )
    await (await SqliteExecutionStore.open(path)).create(execution, events)
