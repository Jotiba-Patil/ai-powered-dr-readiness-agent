import json
from datetime import UTC, datetime

from dr_agent.core.analyzer import run_analysis
from dr_agent.llm.fake import FakeProvider
from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DependencyHealth
from dr_agent.models.runbook import Runbook, Step
from dr_agent.utils.errors import AnalysisError

_FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _clock() -> datetime:
    return _FIXED_TIME


def _runbook() -> Runbook:
    return Runbook(
        service_name="Svc",
        system_owner="Dana",
        rto_minutes=60,
        rpo_minutes=15,
        raw_markdown="# Svc\n\nRevert on failure.\n",
        steps=[
            Step(
                step_number=1,
                action="First",
                owner="Dana",
                estimated_minutes=5,
                validation_command="check",
            ),
            Step(
                step_number=2,
                action="Second",
                owner="Dana",
                estimated_minutes=5,
                validation_command="check",
            ),
        ],
    )


def _llm_response(**overrides: object) -> str:
    base: dict[str, object] = {
        "stepDependencies": [{"stepNumber": 2, "dependsOn": [1]}],
        "singlePointsOfFailure": [
            {
                "description": "Only Dana knows this",
                "affectedSteps": [1],
                "mitigationSuggestion": "Cross-train",
            }
        ],
        "gapAnalysis": [
            {
                "type": "VAGUE_INSTRUCTION",
                "description": "Step 1 is vague",
                "severity": "LOW",
                "recommendation": "Be specific",
            }
        ],
        "suggestions": [{"priority": 1, "title": "Improve", "detail": "Do X"}],
        "summary": "This is a reasonably solid runbook overall, evidence-based summary.",
        "riskScore": 15,
    }
    base.update(overrides)
    return json.dumps(base)


async def test_successful_llm_analysis_merges_into_the_report() -> None:
    llm = FakeProvider([_llm_response()])
    report = await run_analysis(
        _runbook(),
        [],
        llm,
        runbook_file="r.md",
        inventory_file="i.json",
        agent_version="0.1.0",
        clock=_clock,
    )

    assert report.ai_analysis_available is True
    assert report.ai_note is None
    assert report.risk_score == 15
    assert report.summary == "This is a reasonably solid runbook overall, evidence-based summary."
    assert len(report.single_points_of_failure) == 1
    assert report.meta.analyzed_at == _FIXED_TIME


async def test_llm_step_dependency_feeds_the_execution_plan() -> None:
    llm = FakeProvider([_llm_response()])
    report = await run_analysis(
        _runbook(), [], llm, runbook_file="r.md", inventory_file="i.json", agent_version="v"
    )
    # step 2 was inferred to depend on step 1 -> two phases, not one.
    assert [phase.steps for phase in report.execution_plan] == [[1], [2]]


async def test_llm_cannot_reintroduce_a_rule_owned_gap_type() -> None:
    llm = FakeProvider(
        [
            _llm_response(
                gapAnalysis=[
                    {
                        "type": "NO_VALIDATION",
                        "description": "duplicate of the rule check",
                        "severity": "LOW",
                        "recommendation": "n/a",
                    }
                ]
            )
        ]
    )
    report = await run_analysis(
        _runbook(), [], llm, runbook_file="r.md", inventory_file="i.json", agent_version="v"
    )
    no_validation_gaps = [g for g in report.gap_analysis if g.type.value == "NO_VALIDATION"]
    assert no_validation_gaps == []  # every step already has a validation command


async def test_graceful_degradation_on_llm_failure() -> None:
    llm = FakeProvider([], transport_error=AnalysisError("model unreachable"))
    report = await run_analysis(
        _runbook(), [], llm, runbook_file="r.md", inventory_file="i.json", agent_version="v"
    )

    assert report.ai_analysis_available is False
    assert report.ai_note is not None
    assert "model unreachable" in report.ai_note
    assert report.single_points_of_failure == []
    assert report.suggestions == []
    assert report.risk_score >= 0  # falls back to the rule-based score


async def test_degraded_report_still_includes_rule_based_gaps() -> None:
    dep_health = [DependencyHealth(name="db", actual_status=DependencyStatus.DOWN, impact="x")]
    llm = FakeProvider([], transport_error=AnalysisError("down"))
    report = await run_analysis(
        _runbook(), dep_health, llm, runbook_file="r.md", inventory_file="i.json", agent_version="v"
    )
    assert any(g.type.value == "UNVERIFIED_DEPENDENCY" for g in report.gap_analysis)


async def test_llm_dependency_on_unknown_step_is_ignored() -> None:
    llm = FakeProvider([_llm_response(stepDependencies=[{"stepNumber": 2, "dependsOn": [99]}])])
    report = await run_analysis(
        _runbook(), [], llm, runbook_file="r.md", inventory_file="i.json", agent_version="v"
    )
    # unknown dependency (99) is dropped, so both steps end up with no unresolved deps.
    assert report.execution_plan[0].steps == [1, 2]


async def test_llm_entry_for_an_unknown_step_number_is_ignored() -> None:
    llm = FakeProvider([_llm_response(stepDependencies=[{"stepNumber": 99, "dependsOn": [1]}])])
    report = await run_analysis(
        _runbook(), [], llm, runbook_file="r.md", inventory_file="i.json", agent_version="v"
    )
    # step 99 does not exist in the runbook, so the whole entry is dropped.
    assert report.execution_plan[0].steps == [1, 2]
