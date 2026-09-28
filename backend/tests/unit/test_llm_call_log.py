import random

import httpx
import pytest
import structlog
from structlog.testing import capture_logs

from dr_agent.llm.call_log import usage_from
from dr_agent.llm.ollama import OllamaProvider
from dr_agent.llm.openai_compatible import OpenAICompatibleProvider
from dr_agent.utils.errors import AnalysisError

RUNBOOK_PROMPT = "runbook text that must never be logged"


async def _noop_sleep(_seconds: float) -> None:
    return None


def _clock() -> float:
    return 0.0


def _openai(handler: httpx.MockTransport) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        httpx.AsyncClient(transport=handler),
        base_url="https://api.mistral.ai/v1",
        model="mistral-small-latest",
        max_tokens=64,
        rng=random.Random(1),
        api_key="fake-key-1",
        max_retries=1,
        sleeper=_noop_sleep,
        clock=_clock,
    )


def _ollama(handler: httpx.MockTransport) -> OllamaProvider:
    return OllamaProvider(
        httpx.AsyncClient(transport=handler),
        base_url="http://localhost:11434",
        model="qwen2.5:3b-instruct",
        max_tokens=64,
        rng=random.Random(1),
        max_retries=1,
        sleeper=_noop_sleep,
        clock=_clock,
    )


def _llm_calls(logs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [entry for entry in logs if entry["event"] == "llm_call"]


async def test_openai_success_logs_metadata_and_usage_without_prompt_text() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        body = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        }
        return httpx.Response(200, json=body)

    structlog.reset_defaults()
    with capture_logs() as logs:
        await _openai(httpx.MockTransport(handler)).generate(
            system_prompt="sys", user_prompt=RUNBOOK_PROMPT, schema={}
        )

    [entry] = _llm_calls(logs)
    assert entry["log_level"] == "info"
    assert entry["provider"] == "openai_compatible"
    assert entry["model"] == "mistral-small-latest"
    assert entry["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert entry["outcome"] == "ok"
    assert entry["status"] == 200
    assert entry["attempt"] == 1
    assert entry["total_tokens"] == 15
    assert entry["prompt_chars"] == len("sys") + len(RUNBOOK_PROMPT)
    assert RUNBOOK_PROMPT not in str(logs)
    assert "fake-key-1" not in str(logs)


async def test_openai_retry_then_failure_logs_every_attempt() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="overloaded")

    structlog.reset_defaults()
    with capture_logs() as logs, pytest.raises(AnalysisError):
        await _openai(httpx.MockTransport(handler)).generate(
            system_prompt="sys", user_prompt="user", schema={}
        )

    entries = _llm_calls(logs)
    assert [entry["outcome"] for entry in entries] == ["retry", "failed"]
    assert all(entry["log_level"] == "warning" and entry["status"] == 503 for entry in entries)


async def test_openai_rejected_request_logs_failed_once() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key")

    structlog.reset_defaults()
    with capture_logs() as logs, pytest.raises(AnalysisError):
        await _openai(httpx.MockTransport(handler)).generate(
            system_prompt="sys", user_prompt="user", schema={}
        )

    [entry] = _llm_calls(logs)
    assert entry["outcome"] == "failed"
    assert entry["status"] == 401


async def test_ollama_logs_retry_then_success_with_eval_counts() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        body = {"message": {"content": "{}"}, "prompt_eval_count": 40, "eval_count": 5}
        return httpx.Response(200, json=body)

    structlog.reset_defaults()
    with capture_logs() as logs:
        await _ollama(httpx.MockTransport(handler)).generate(
            system_prompt="sys", user_prompt=RUNBOOK_PROMPT, schema={}
        )

    retry, ok = _llm_calls(logs)
    assert retry["outcome"] == "retry"
    assert "status" not in retry
    assert ok["outcome"] == "ok"
    assert ok["provider"] == "ollama"
    assert ok["prompt_tokens"] == 40
    assert ok["completion_tokens"] == 5
    assert RUNBOOK_PROMPT not in str(logs)


def test_usage_from_ignores_missing_or_malformed_values() -> None:
    assert usage_from(None) == {}
    assert usage_from({"usage": {"prompt_tokens": "12", "total_tokens": True}}) == {}
