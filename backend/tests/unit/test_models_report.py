import copy

import pytest
from pydantic import ValidationError

from dr_agent import __version__
from dr_agent.models import DRReadinessReport, RiskLevel, risk_level_from_score


def report_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "meta": {
            "analyzedAt": "2026-09-21T10:00:00Z",
            "runbookFile": "estimate-service.md",
            "inventoryFile": "healthy.json",
            "agentVersion": __version__,
            "analysisTimeMs": 1234.5,
        },
        "serviceSummary": {
            "name": "Estimate Service",
            "owner": "Dana",
            "statedRTO": 60,
            "statedRPO": 15,
        },
        "riskScore": 42,
        "rtoAnalysis": {
            "feasible": True,
            "totalEstimatedMinutes": 40,
            "statedRtoMinutes": 60,
            "bufferMinutes": 20,
            "bottleneckSteps": [2],
        },
        "dependencyHealth": [
            {"name": "pg", "actualStatus": "NOT_IN_INVENTORY", "impact": "Steps 1, 2"}
        ],
        "singlePointsOfFailure": [
            {"description": "One DBA", "affectedSteps": [1], "mitigationSuggestion": "Cross-train"}
        ],
        "gapAnalysis": [
            {
                "type": "NO_VALIDATION",
                "description": "No checks",
                "severity": "MEDIUM",
                "recommendation": "Add checks",
            }
        ],
        "executionPlan": [
            {"phase": 1, "steps": [1], "estimatedMinutes": 10, "gate": "DB restored"}
        ],
        "suggestions": [{"priority": 1, "title": "Add checks", "detail": "curl /health"}],
        "summary": "Ready with caveats.",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, RiskLevel.LOW),
        (25, RiskLevel.LOW),
        (26, RiskLevel.MEDIUM),
        (50, RiskLevel.MEDIUM),
        (51, RiskLevel.HIGH),
        (80, RiskLevel.HIGH),
        (81, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_risk_level_boundaries(score: int, level: RiskLevel) -> None:
    assert risk_level_from_score(score) is level


def test_report_derives_risk_level_and_serializes_camel_case() -> None:
    report = DRReadinessReport.model_validate(report_data())
    assert report.risk_level is RiskLevel.MEDIUM
    dumped = report.to_json_dict()
    assert dumped["riskLevel"] == "MEDIUM"
    assert dumped["riskScore"] == 42
    assert dumped["serviceSummary"] == {
        "name": "Estimate Service",
        "owner": "Dana",
        "statedRTO": 60.0,
        "statedRPO": 15.0,
    }
    assert dumped["aiAnalysisAvailable"] is True


def test_report_round_trips_including_risk_level() -> None:
    report = DRReadinessReport.model_validate(report_data())
    again = DRReadinessReport.model_validate(report.to_json_dict())
    assert again == report


def test_report_level_follows_score() -> None:
    report = DRReadinessReport.model_validate(report_data(riskScore=90))
    assert report.risk_level is RiskLevel.CRITICAL


def test_inconsistent_risk_level_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        DRReadinessReport.model_validate(report_data(riskLevel="LOW", riskScore=90))


def test_risk_level_with_snake_case_input() -> None:
    data = report_data()
    data["risk_score"] = data.pop("riskScore")
    data["risk_level"] = "MEDIUM"
    assert DRReadinessReport.model_validate(data).risk_score == 42


@pytest.mark.parametrize("score", [-1, 101, 4.5, "80", "high", True])
def test_risk_score_must_be_int_in_range(score: object) -> None:
    with pytest.raises(ValidationError):
        DRReadinessReport.model_validate(report_data(riskScore=score))


def test_bool_score_with_level_does_not_crash_the_before_validator() -> None:
    with pytest.raises(ValidationError):
        DRReadinessReport.model_validate(report_data(riskScore=True, riskLevel="LOW"))


def test_non_dict_input_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DRReadinessReport.model_validate("nope")


def test_negative_buffer_is_allowed() -> None:
    data = copy.deepcopy(report_data())
    data["rtoAnalysis"] = {
        "feasible": False,
        "totalEstimatedMinutes": 60,
        "statedRtoMinutes": 15,
        "bufferMinutes": -45,
    }
    report = DRReadinessReport.model_validate(data)
    assert report.rto_analysis.buffer_minutes == -45
    assert report.rto_analysis.bottleneck_steps == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("suggestions", 0, "priority"), 0),
        (("suggestions", 0, "priority"), 6),
        (("gapAnalysis", 0, "type"), "MISSING_COFFEE"),
        (("gapAnalysis", 0, "severity"), "CRITICAL"),
        (("dependencyHealth", 0, "actualStatus"), "UNKNOWN"),
        (("dependencyHealth", 0, "runbookAssumes"), "broken"),
        (("executionPlan", 0, "phase"), 0),
        (("meta", "analysisTimeMs"), -1),
    ],
)
def test_report_rejects_invalid_nested_values(path: tuple[str | int, ...], value: object) -> None:
    data = copy.deepcopy(report_data())
    node: object = data
    for key in path[:-1]:
        node = node[key]  # type: ignore[index]  # test-only navigation of nested JSON
    node[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        DRReadinessReport.model_validate(data)


def test_ai_unavailable_requires_note() -> None:
    with pytest.raises(ValidationError, match="aiNote"):
        DRReadinessReport.model_validate(report_data(aiAnalysisAvailable=False))
    ok = DRReadinessReport.model_validate(
        report_data(aiAnalysisAvailable=False, aiNote="AI analysis unavailable")
    )
    assert ok.ai_note == "AI analysis unavailable"
