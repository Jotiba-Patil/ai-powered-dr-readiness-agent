"""Phase 14 exit: live runs against the mock MCP server change the next analysis.

Two live runs of the executable sample, each with a failing smoke test that is
rolled back, are stored next to their analyses in one database file. The next
analysis of the same runbook then carries the measured history and a
HISTORICAL gap for step 5, and so does the prompt's `<history>` block.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

from mcp import Client

from conftest import mock_checker
from dr_agent.core.parser import parse_runbook
from dr_agent.execution.analysis_link import analysis_ref, phase_edges
from dr_agent.execution.decisions import Approve, ReportOutcome
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import CallKind, ExecutionMode, ExecutionState, StepState
from dr_agent.execution.policy_file import load_policy
from dr_agent.execution.session import ExecutionLimits
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.history.models import AnalysisRecord, AnalysisSource, Provenance
from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.knowledge.service import KnowledgeBase
from dr_agent.knowledge.source import SqliteKnowledgeSource
from dr_agent.llm.disabled import DisabledProvider
from dr_agent.llm.fake import FakeProvider
from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.mock_mcp.state import Scenario, ToolFault
from dr_agent.models.report import DRReadinessReport, GapType
from dr_agent.service import analyze_runbook
from dr_agent.tools.mcp_executor import McpToolExecutor

REPO = Path(__file__).resolve().parents[3]
RUNBOOK = parse_runbook(
    (REPO / "mock-data/runbooks/estimate-service-executable.md").read_text("utf-8")
)
APPROVERS = ("Ann", "Ben")
NOW = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


async def _analyze(knowledge: KnowledgeBase, llm: object = None) -> DRReadinessReport:
    return await analyze_runbook(
        RUNBOOK,
        None,
        llm=llm or DisabledProvider(),  # type: ignore[arg-type]  # a provider either way
        checker=mock_checker(),
        runbook_label="estimate-service-executable.md",
        inventory_label=None,
        knowledge=knowledge,
    )


async def _store(path: Path, analysis_id: str, report: DRReadinessReport) -> None:
    provenance = Provenance(llm_provider="none", prompt_version="analysis/2", agent_version="t")
    record = AnalysisRecord(
        id=analysis_id,
        source=AnalysisSource.CLI,
        created_at=NOW,
        completed_at=NOW,
        runbook_label="estimate-service-executable.md",
        runbook=RUNBOOK,
        report=report,
        provenance=provenance,
    )
    await (await SqliteAnalysisStore.open(path)).save(record)


async def _failing_live_run(path: Path, analysis_id: str, report: DRReadinessReport) -> None:
    """Smoke test fails, its DNS switch is rolled back, the run is closed as FAILED."""
    env = DrEnvironment(Scenario(faults={"smoke_run": ToolFault(fail_on_calls=[1])}))
    server = build_server(env)
    async with McpToolExecutor({"drsim": lambda: Client(server)}, rng=random.Random(0)) as tools:
        engine = ExecutionEngine(
            store=await SqliteExecutionStore.open(path),
            executor=tools,
            policy=load_policy(REPO / "execution-policy.json"),
            limits=ExecutionLimits(enabled=True, allow_live=True),
        )
        execution = await engine.create(
            RUNBOOK,
            mode=ExecutionMode.LIVE,
            started_by="Olivia",
            runbook_label="estimate-service-executable.md",
            inferred=phase_edges(report.execution_plan),
            analysis=analysis_ref(analysis_id, report),
        )
        for run in execution.steps:
            assert run.call is not None
            destructive = (
                run.call.risk_class is not None and run.call.risk_class.value == "destructive"
            )
            for name in APPROVERS[: 2 if destructive else 1]:
                await engine.decide(
                    execution.id, run.step_number, Approve(name, run.call.call_hash)
                )
        await engine.start(execution.id, "Olivia")
        await engine.advance(execution.id)
        await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "primary is down"))
        execution = await engine.advance(execution.id)
        rollback = execution.step(5).rollback
        assert execution.step(5).state is StepState.FAILED
        assert rollback is not None
        for name in APPROVERS:
            await engine.decide(
                execution.id, 5, Approve(name, rollback.call_hash, kind=CallKind.ROLLBACK)
            )
        await engine.rollback(execution.id, 5, "Olivia")
        closed = await engine.close(execution.id, "Olivia", "failover abandoned")
        assert closed.state is ExecutionState.FAILED


async def test_live_runs_produce_findings_in_the_next_analysis(tmp_path: Path) -> None:
    path = tmp_path / "dr-agent.db"
    knowledge = KnowledgeBase(SqliteKnowledgeSource(path))
    await SqliteAnalysisStore.open(path)  # an empty, migrated database
    first = await _analyze(knowledge)
    assert first.historical_insights is None
    assert not [g for g in first.gap_analysis if g.type is GapType.HISTORICAL]

    for number in (1, 2):
        report = await _analyze(knowledge)
        await _store(path, f"analysis-{number}", report)
        await _failing_live_run(path, f"analysis-{number}", report)

    llm = FakeProvider(['{"summary": "s", "riskScore": 50}'])
    after = await _analyze(knowledge, llm)
    history = after.historical_insights
    assert history is not None
    assert (history.live_runs, history.analyses_considered) == (2, 2)
    step5 = next(s for s in history.steps if s.step_number == 5)
    assert (step5.live_runs, step5.rolled_back) == (2, 2)
    assert [e.state for e in history.executions] == ["FAILED", "FAILED"]
    findings = [g.description for g in after.gap_analysis if g.type is GapType.HISTORICAL]
    assert findings == ["Step 5 failed or was rolled back in 2 of 2 past live runs."]
    prompt = llm.calls[0][1]
    assert '"rolledBack": 2' in prompt
    assert "failover abandoned" not in prompt  # reasons never reach the model
