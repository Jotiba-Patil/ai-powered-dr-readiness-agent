"""The analyzer with a service history (Phase 14): rule gaps, score, prompt, report section."""

from __future__ import annotations

import json
from pathlib import Path

from dr_agent import __version__
from dr_agent.core.analyzer import run_analysis
from dr_agent.core.parser import parse_runbook
from dr_agent.llm.fake import FakeProvider
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.report import GapType
from dr_agent.utils.errors import AnalysisError

ROOT = Path(__file__).resolve().parents[3]
HISTORY = ServiceHistory.model_validate_json(
    (ROOT / "backend/tests/fixtures/history/estimate-service.json").read_text("utf-8")
)
RUNBOOK = parse_runbook((ROOT / "mock-data/runbooks/estimate-service.md").read_text("utf-8"))


def _llm_reply(extra_gap_type: str = "VAGUE_INSTRUCTION") -> str:
    return json.dumps(
        {
            "gapAnalysis": [
                {
                    "type": extra_gap_type,
                    "description": "made up",
                    "severity": "HIGH",
                    "recommendation": "x",
                }
            ],
            "summary": "Summary.",
            "riskScore": 40,
        }
    )


async def _analyze(llm: FakeProvider, **options: object) -> tuple[object, FakeProvider]:
    report = await run_analysis(
        RUNBOOK,
        [],
        llm,
        runbook_file="r.md",
        inventory_file="(none)",
        agent_version=__version__,
        **options,  # type: ignore[arg-type]  # history / history_in_prompt only
    )
    return report, llm


async def test_rules_only_score_counts_history_gaps() -> None:
    offline = AnalysisError("model offline")
    without, _ = await _analyze(FakeProvider([], transport_error=offline))
    with_history, _ = await _analyze(FakeProvider([], transport_error=offline), history=HISTORY)
    assert with_history.risk_score == without.risk_score + 46  # 2 HIGH (15) + 2 MEDIUM (8)
    kinds = [g.type for g in with_history.gap_analysis]
    assert kinds.count(GapType.HISTORICAL) == 4
    assert with_history.historical_insights == HISTORY


async def test_the_model_cannot_add_historical_gaps() -> None:
    report, _ = await _analyze(FakeProvider([_llm_reply("HISTORICAL")]), history=HISTORY)
    made_up = [g for g in report.gap_analysis if g.description == "made up"]
    assert made_up == []


async def test_history_can_be_kept_out_of_the_prompt() -> None:
    report, llm = await _analyze(
        FakeProvider([_llm_reply()]), history=HISTORY, history_in_prompt=False
    )
    assert "<history>" not in llm.calls[0][1]
    assert report.historical_insights == HISTORY  # still reported and still used by rules
    assert any(g.type is GapType.HISTORICAL for g in report.gap_analysis)
