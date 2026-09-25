import json
import random

import httpx
import pytest

from dr_agent.llm.openai_compatible import OpenAICompatibleProvider, ResponseFormat
from dr_agent.utils.errors import AnalysisError

FAKE_KEY = "fake-key-1"
Handler = httpx.MockTransport


async def _noop_sleep(_seconds: float) -> None:
    return None


def _ok(content: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _provider(
    handler: Handler,
    *,
    api_key: str | None = FAKE_KEY,
    response_format: ResponseFormat = "json_schema",
    max_retries: int = 3,
    base_url: str = "https://api.mistral.ai/v1/",
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        httpx.AsyncClient(transport=handler),
        base_url=base_url,
        model="mistral-small-latest",
        max_tokens=512,
        rng=random.Random(1),
        api_key=api_key,
        response_format=response_format,
        max_retries=max_retries,
        sleeper=_noop_sleep,
    )


async def _generate(provider: OpenAICompatibleProvider) -> str:
    return await provider.generate(system_prompt="sys", user_prompt="user", schema={"a": 1})


async def test_posts_chat_completion_with_bearer_key_and_json_schema() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return _ok('{"riskScore": 10}')

    result = await _generate(_provider(Handler(handler)))

    request = captured["request"]
    body = json.loads(request.read())
    assert result == '{"riskScore": 10}'
    assert str(request.url) == "https://api.mistral.ai/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert body["model"] == "mistral-small-latest"
    assert body["max_tokens"] == 512
    assert body["temperature"] == 0
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "dr_readiness_analysis", "schema": {"a": 1}, "strict": False},
    }


async def test_json_object_mode_puts_the_schema_in_the_system_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return _ok("{}")

    await _generate(_provider(Handler(handler), response_format="json_object"))

    body = json.loads(captured["body"])
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["content"].endswith('JSON schema:\n{"a": 1}')


async def test_no_authorization_header_without_a_key() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return _ok("{}")

    await _generate(_provider(Handler(handler), api_key=None))
    assert "authorization" not in captured["request"].headers


@pytest.mark.parametrize("status", [408, 429, 500, 503])
async def test_retryable_statuses_are_retried(status: int) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(status) if attempts["count"] < 3 else _ok("recovered")

    assert await _generate(_provider(Handler(handler))) == "recovered"
    assert attempts["count"] == 3


async def test_transport_errors_are_retried_then_raise() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(AnalysisError, match="after retries") as caught:
        await _generate(_provider(Handler(handler), max_retries=2))

    assert attempts["count"] == 3
    assert "timed out" in str(caught.value.details)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_client_errors_fail_fast_without_leaking_the_key(status: int) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(status, json={"error": f"Incorrect API key provided: {FAKE_KEY}"})

    with pytest.raises(AnalysisError, match=f"HTTP {status}") as caught:
        await _generate(_provider(Handler(handler)))

    assert attempts["count"] == 1
    assert caught.value.details is not None
    assert caught.value.details["status"] == status
    assert FAKE_KEY not in str(caught.value.details)
    assert "***" in str(caught.value.details["reason"])


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"unexpected": True}),
    ],
)
async def test_unexpected_response_shape_raises(response: httpx.Response) -> None:
    with pytest.raises(AnalysisError, match="unexpected response shape"):
        await _generate(_provider(Handler(lambda _request: response)))


async def test_missing_content_raises() -> None:
    with pytest.raises(AnalysisError, match="no message content"):
        await _generate(_provider(Handler(lambda _request: _ok(None))))


async def test_url_credentials_are_scrubbed_from_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    provider = _provider(
        Handler(handler), max_retries=0, base_url="https://user:hunter2@llm.internal/v1"
    )
    with pytest.raises(AnalysisError) as caught:
        await _generate(provider)

    assert "hunter2" not in str(caught.value.details)
