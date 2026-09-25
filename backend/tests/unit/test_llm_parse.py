import json

import pytest

from dr_agent.llm.fake import FakeProvider
from dr_agent.llm.parse import get_llm_analysis
from dr_agent.utils.errors import AnalysisError

_VALID = {
    "stepDependencies": [],
    "singlePointsOfFailure": [],
    "gapAnalysis": [],
    "suggestions": [],
    "summary": "All good but here is one improvement anyway.",
    "riskScore": 20,
}


async def test_valid_response_on_first_try() -> None:
    provider = FakeProvider([json.dumps(_VALID)])
    result = await get_llm_analysis(provider, system_prompt="sys", user_prompt="user")
    assert result.risk_score == 20
    assert len(provider.calls) == 1


async def test_malformed_json_is_retried_once_and_then_succeeds() -> None:
    provider = FakeProvider(["not json at all", json.dumps(_VALID)])
    result = await get_llm_analysis(provider, system_prompt="sys", user_prompt="user")
    assert result.risk_score == 20
    assert len(provider.calls) == 2
    assert "valid JSON" in provider.calls[1][1]


async def test_malformed_json_twice_raises_after_one_retry() -> None:
    provider = FakeProvider(["not json", "still not json"])
    with pytest.raises(AnalysisError):
        await get_llm_analysis(provider, system_prompt="sys", user_prompt="user")
    assert len(provider.calls) == 2


async def test_schema_invalid_json_is_retried_with_corrected_response() -> None:
    invalid = json.dumps({**_VALID, "riskScore": 500})  # out of 0-100 range
    provider = FakeProvider([invalid, json.dumps(_VALID)])
    result = await get_llm_analysis(provider, system_prompt="sys", user_prompt="user")
    assert result.risk_score == 20
    assert len(provider.calls) == 2
    assert "failed validation" in provider.calls[1][1]


async def test_schema_invalid_twice_raises_after_one_retry() -> None:
    invalid = json.dumps({**_VALID, "riskScore": 500})
    provider = FakeProvider([invalid, invalid])
    with pytest.raises(AnalysisError):
        await get_llm_analysis(provider, system_prompt="sys", user_prompt="user")
    assert len(provider.calls) == 2


async def test_missing_required_field_is_rejected() -> None:
    missing_summary = {k: v for k, v in _VALID.items() if k != "summary"}
    provider = FakeProvider([json.dumps(missing_summary), json.dumps(missing_summary)])
    with pytest.raises(AnalysisError):
        await get_llm_analysis(provider, system_prompt="sys", user_prompt="user")
