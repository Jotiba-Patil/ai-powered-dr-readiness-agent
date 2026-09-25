import random

import httpx
import pytest

from dr_agent.llm.ollama import OllamaProvider
from dr_agent.utils.errors import AnalysisError


async def _noop_sleep(_seconds: float) -> None:
    return None


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_successful_call_returns_message_content() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"message": {"content": '{"riskScore": 10}'}})

    client = _client(httpx.MockTransport(handler))
    provider = OllamaProvider(
        client,
        base_url="http://localhost:11434",
        model="qwen2.5:3b-instruct",
        max_tokens=512,
        rng=random.Random(1),
        sleeper=_noop_sleep,
    )

    result = await provider.generate(system_prompt="sys", user_prompt="user", schema={"a": 1})

    assert result == '{"riskScore": 10}'
    assert b"qwen2.5:3b-instruct" in captured["body"]


async def test_retries_on_transport_error_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    client = _client(httpx.MockTransport(handler))
    provider = OllamaProvider(
        client,
        base_url="http://localhost:11434",
        model="m",
        max_tokens=10,
        rng=random.Random(1),
        sleeper=_noop_sleep,
        max_retries=3,
    )

    result = await provider.generate(system_prompt="sys", user_prompt="user", schema={})

    assert result == "ok"
    assert attempts["count"] == 3


async def test_raises_analysis_error_after_exhausting_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(httpx.MockTransport(handler))
    provider = OllamaProvider(
        client,
        base_url="http://localhost:11434",
        model="m",
        max_tokens=10,
        rng=random.Random(1),
        sleeper=_noop_sleep,
        max_retries=2,
    )

    with pytest.raises(AnalysisError):
        await provider.generate(system_prompt="sys", user_prompt="user", schema={})


async def test_5xx_response_is_retried() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(500)
        return httpx.Response(200, json={"message": {"content": "recovered"}})

    client = _client(httpx.MockTransport(handler))
    provider = OllamaProvider(
        client,
        base_url="http://localhost:11434",
        model="m",
        max_tokens=10,
        rng=random.Random(1),
        sleeper=_noop_sleep,
        max_retries=3,
    )

    result = await provider.generate(system_prompt="sys", user_prompt="user", schema={})
    assert result == "recovered"


async def test_sleeper_is_awaited_between_retries() -> None:
    calls: list[float] = []

    async def spy_sleep(seconds: float) -> None:
        calls.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    client = _client(httpx.MockTransport(handler))
    provider = OllamaProvider(
        client,
        base_url="http://localhost:11434",
        model="m",
        max_tokens=10,
        rng=random.Random(1),
        sleeper=spy_sleep,
        max_retries=2,
    )

    with pytest.raises(AnalysisError):
        await provider.generate(system_prompt="sys", user_prompt="user", schema={})

    assert len(calls) == 2  # one sleep between each of the 3 attempts, not after the last


async def test_error_reason_never_contains_url_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    provider = OllamaProvider(
        _client(httpx.MockTransport(handler)),
        base_url="http://admin:hunter2@localhost:11434",
        model="m",
        max_tokens=10,
        rng=random.Random(1),
        sleeper=_noop_sleep,
        max_retries=0,
    )

    with pytest.raises(AnalysisError) as caught:
        await provider.generate(system_prompt="sys", user_prompt="user", schema={})

    reason = str(caught.value.details["reason"])
    assert "hunter2" not in reason
    assert "http://***@localhost:11434/api/chat" in reason
