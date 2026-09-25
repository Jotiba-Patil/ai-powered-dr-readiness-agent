"""Analyses for `dr-agent analyze` and `execute`: run and store one, or load a stored one.

A new analysis uses the knowledge base (ADR 0009) when it is on, and is saved
to the history (ADR 0007) unless `--no-save` is given
or `HISTORY_ENABLED=false`; a failed save is reported but never fails the run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dr_agent.config import Settings
from dr_agent.health.base import HealthChecker
from dr_agent.history.models import AnalysisRecord, AnalysisSource
from dr_agent.history.service import History, open_history, provenance
from dr_agent.knowledge.service import open_knowledge
from dr_agent.llm.base import LLMProvider
from dr_agent.loaders import load_inventory, read_text_file
from dr_agent.service import analyze_runbook, parse_markdown
from dr_agent.utils.errors import HistoryDisabledError

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CliAnalysis:
    record: AnalysisRecord
    saved: bool
    stale: bool = False


async def run_analysis(
    settings: Settings,
    runbook_path: Path,
    inventory_path: Path | None,
    *,
    llm: LLMProvider,
    checker: HealthChecker,
    save: bool,
    clock: Clock = lambda: datetime.now(UTC),
) -> CliAnalysis:
    runbook = parse_markdown(read_text_file(runbook_path))
    inventory = load_inventory(inventory_path) if inventory_path else None
    created_at = clock()
    report = await analyze_runbook(
        runbook,
        inventory,
        llm=llm,
        checker=checker,
        runbook_label=runbook_path.name,
        inventory_label=inventory_path.name if inventory_path else None,
        knowledge=open_knowledge(settings),
    )
    record = AnalysisRecord(
        id=uuid4().hex,
        source=AnalysisSource.CLI,
        created_at=created_at,
        completed_at=clock(),
        runbook_label=runbook_path.name,
        runbook=runbook,
        inventory_label=inventory_path.name if inventory_path else None,
        inventory=inventory,
        report=report,
        provenance=provenance(settings),
    )
    history = await open_history(settings) if save else None
    saved = await history.save(record) if history is not None else False
    return CliAnalysis(record, saved)


async def require_history(settings: Settings) -> History:
    history = await open_history(settings)
    if history is None:
        raise HistoryDisabledError("analysis history is disabled (HISTORY_ENABLED)")
    return history


async def stored_analysis(settings: Settings, analysis_id: str) -> CliAnalysis:
    """`NotFoundError` for an unknown id; `HistoryDisabledError` while history is off."""
    history = await require_history(settings)
    record = await history.store.get(analysis_id)
    return CliAnalysis(record, saved=True, stale=history.is_stale(record.completed_at))
