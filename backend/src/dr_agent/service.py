"""The shared service layer: the one pipeline both the CLI and the API call.

`parse_markdown()` is split out from `analyze_runbook()` so the API can reject
a bad runbook with 422 before queueing a (minutes-long) analysis job, without
parsing twice. Framework-free: no FastAPI, Typer or Rich imports here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from dr_agent import __version__
from dr_agent.core.analyzer import run_analysis
from dr_agent.core.parser import parse_runbook
from dr_agent.health.base import HealthChecker
from dr_agent.health.dependency_check import check_dependencies
from dr_agent.knowledge.service import KnowledgeBase
from dr_agent.llm.base import LLMProvider
from dr_agent.models.inventory import ServiceStatus, SystemInventory
from dr_agent.models.report import DRReadinessReport
from dr_agent.models.runbook import Runbook
from dr_agent.utils.logging import get_logger
from dr_agent.utils.timing import Clock, Stopwatch

NO_INVENTORY_LABEL = "(none)"

_log = get_logger("dr_agent.service")


def parse_markdown(raw_markdown: str, *, timer: Clock = time.perf_counter) -> Runbook:
    """Parse and validate a runbook; raises `ParseError`. Logs timing, never content."""
    watch = Stopwatch(timer)
    runbook = parse_runbook(raw_markdown)
    _log.info(
        "runbook_parsed",
        service=runbook.service_name,
        steps=len(runbook.steps),
        warnings=len(runbook.parser_warnings),
        duration_ms=round(watch.stop(), 2),
    )
    return runbook


async def validate_inventory(
    inventory: SystemInventory, checker: HealthChecker
) -> list[ServiceStatus]:
    """Health-check every inventory service (the CLI's `validate` command)."""
    return await checker.check_all(inventory.services)


async def analyze_runbook(
    runbook: Runbook,
    inventory: SystemInventory | None,
    *,
    llm: LLMProvider,
    checker: HealthChecker,
    runbook_label: str,
    inventory_label: str | None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    timer: Clock = time.perf_counter,
    knowledge: KnowledgeBase | None = None,
) -> DRReadinessReport:
    """Health-check the runbook's dependencies, then run rules + LLM analysis.

    With a `knowledge` base, what past analyses and live runs of this service
    showed is added (HISTORICAL gaps, `historicalInsights`, the prompt's
    `<history>` block); without history the report is exactly as before.

    With no inventory every dependency is reported `NOT_IN_INVENTORY` (nothing
    could be verified), which the rule-based gaps then flag as unverified.
    """
    total = Stopwatch(timer)
    health_watch = Stopwatch(timer)
    dependency_health = await check_dependencies(runbook, inventory or SystemInventory(), checker)
    health_ms = health_watch.stop()
    history = await knowledge.insights_for(runbook) if knowledge else None

    report = await run_analysis(
        runbook,
        dependency_health,
        llm,
        runbook_file=runbook_label,
        inventory_file=inventory_label or NO_INVENTORY_LABEL,
        agent_version=__version__,
        clock=clock,
        timer=timer,
        history=history,
        history_in_prompt=knowledge.in_prompt if knowledge else False,
    )
    analysis_ms = report.meta.analysis_time_ms
    total_ms = total.stop()
    _log.info(
        "analysis_completed",
        service=runbook.service_name,
        risk_score=report.risk_score,
        ai_analysis_available=report.ai_analysis_available,
        history_steps=len(history.steps) if history else 0,
        health_check_ms=round(health_ms, 2),
        analysis_ms=round(analysis_ms, 2),
        total_ms=round(total_ms, 2),
    )
    # The report's analysisTimeMs covers the whole pipeline, not only the LLM stage.
    meta = report.meta.model_copy(update={"analysis_time_ms": total_ms})
    return report.model_copy(update={"meta": meta})
