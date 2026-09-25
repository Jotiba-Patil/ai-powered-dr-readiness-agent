"""The SQLite knowledge source and the knowledge base over a real database file."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from exec_support import executable_runbook
from history_support import golden_report, make_record, store_execution
from knowledge_support import finished_run

from dr_agent.config import Settings
from dr_agent.execution.analysis_link import analysis_ref
from dr_agent.execution.models import StepState
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.history.models import AnalysisRecord
from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.knowledge.facts import PastRun
from dr_agent.knowledge.service import KnowledgeBase, open_knowledge
from dr_agent.knowledge.source import SqliteKnowledgeSource


async def _seed(path: Path) -> None:
    """Two analyses, two finished live runs, a dry run and an unlinked live run."""
    analyses = await SqliteAnalysisStore.open(path)
    executions = SqliteExecutionStore(path)
    await analyses.save(make_record("a1", minutes=0))
    await analyses.save(make_record("a2", minutes=10))
    await analyses.save(make_record("other", minutes=5, service="Billing"))
    runs = (("live-1", "a1", 0), ("live-2", "a2", 1), ("orphan", None, 2))
    for execution_id, analysis_id, minute in runs:
        run = finished_run(execution_id, step_minutes={5: (0, 4)}, end_states={5: StepState.FAILED})
        if analysis_id:
            run.execution.analysis = analysis_ref(analysis_id, golden_report())
        run.execution.created_at = run.execution.created_at.replace(minute=minute)
        await executions.create(run.execution, run.events)
    await store_execution(path, "dry-1", "a2")


async def test_source_reads_only_this_services_linked_finished_runs(tmp_path: Path) -> None:
    path = tmp_path / "k.db"
    await _seed(path)
    source = SqliteKnowledgeSource(path)
    assert [a.id for a in await source.analyses("Estimate Service", 10)] == ["a2", "a1"]
    assert [a.id for a in await source.analyses("Estimate Service", 1)] == ["a2"]
    runs = await source.live_runs("Estimate Service", 10)
    assert [r.execution.id for r in runs] == ["live-2", "live-1"]
    assert runs[0].stated_rto_minutes == 60.0
    assert len(runs[0].events) == 5
    assert await source.dry_run_count("Estimate Service") == 1
    assert await source.live_runs("Billing", 10) == []


async def test_knowledge_base_matches_history_to_the_runbook(tmp_path: Path) -> None:
    path = tmp_path / "k.db"
    await _seed(path)
    knowledge = KnowledgeBase(SqliteKnowledgeSource(path), max_runs=5, max_analyses=5)
    history = await knowledge.service_history("Estimate Service")
    assert (history.analyses_considered, history.live_runs, history.dry_runs) == (2, 2, 1)
    insights = await knowledge.insights_for(executable_runbook())
    assert insights is not None
    step5 = next(s for s in insights.steps if s.step_number == 5)
    assert (step5.live_runs, step5.failed) == (2, 2)
    assert (
        await KnowledgeBase(SqliteKnowledgeSource(tmp_path / "empty.db")).insights_for(
            executable_runbook()
        )
        is None
    )


class BrokenSource:
    async def analyses(self, service: str, limit: int) -> list[AnalysisRecord]:
        raise sqlite3.OperationalError("no such table: analyses")

    async def live_runs(self, service: str, limit: int) -> list[PastRun]:
        return []

    async def dry_run_count(self, service: str) -> int:
        return 0


async def test_a_broken_history_never_fails_the_analysis() -> None:
    assert await KnowledgeBase(BrokenSource()).insights_for(executable_runbook()) is None


def test_open_knowledge_follows_the_settings(tmp_path: Path) -> None:
    path = str(tmp_path / "k.db")
    on = open_knowledge(Settings(_env_file=None, db_path=path, knowledge_in_prompt=False))
    assert on is not None
    assert on.in_prompt is False
    assert open_knowledge(Settings(_env_file=None, db_path=path, knowledge_enabled=False)) is None
    assert open_knowledge(Settings(_env_file=None, db_path=path, history_enabled=False)) is None


async def test_a_brand_new_database_is_empty_not_an_error(tmp_path: Path) -> None:
    source = SqliteKnowledgeSource(tmp_path / "fresh.db")  # file does not exist yet
    assert await source.analyses("Estimate Service", 5) == []
    assert await source.live_runs("Estimate Service", 5) == []
    assert await source.dry_run_count("Estimate Service") == 0
