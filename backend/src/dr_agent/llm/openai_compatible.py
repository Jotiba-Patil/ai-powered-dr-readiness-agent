"""OpenAICompatibleProvider: any server that speaks OpenAI's `/chat/completions` API.

One implementation covers hosted APIs (OpenAI, Mistral, Groq, OpenRouter, ...)
and self-hosted servers (vLLM, LM Studio, llama.cpp server), with plain httpx
and no vendor SDK. `base_url` is the API root including its version path, for
example `https://api.openai.com/v1` or `https://api.mistral.ai/v1`.

The API key is sent as a bearer token and is scrubbed from every error detail.
Connection errors, timeouts, 408, 429 and 5xx are retried with exponential
backoff and jitter; any other 4xx (bad key, unknown model, rejected payload)
fails at once because retrying cannot fix it. JSON-decode and schema-validation
retries are the caller's job (`llm/parse.py`), as with `OllamaProvider`.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from typing import Literal

import httpx

from dr_agent.llm.call_log import CallTarget, log_attempt, usage_from
from dr_agent.llm.retry import DEFAULT_MAX_RETRIES, backoff_seconds
from dr_agent.utils.errors import AnalysisError
from dr_agent.utils.logging import REDACTED, scrub_url_credentials
from dr_agent.utils.timing import Clock, Stopwatch

Sleeper = Callable[[float], Awaitable[None]]
ResponseFormat = Literal["json_schema", "json_object"]

_SCHEMA_NAME = "dr_readiness_analysis"
_RETRYABLE_STATUS = frozenset({408, 429})
_ERROR_TEXT_LIMIT = 500


class OpenAICompatibleProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        model: str,
        max_tokens: int,
        rng: random.Random,
        api_key: str | None = None,
        response_format: ResponseFormat = "json_schema",
        timeout_seconds: float = 300.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Sleeper = asyncio.sleep,
        clock: Clock = time.perf_counter,
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._max_tokens = max_tokens
        self._rng = rng
        self._api_key = api_key
        self._response_format = response_format
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._sleeper = sleeper
        self._clock = clock
        self._target = CallTarget("openai_compatible", model, self._url)

    async def generate(
        self, *, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> str:
        payload = self._payload(system_prompt, user_prompt, schema)
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

        prompt_chars = len(system_prompt) + len(user_prompt)
        attempts = self._max_retries + 1
        last_reason = ""
        for attempt in range(attempts):
            watch = Stopwatch(self._clock)
            status: int | None = None
            try:
                response = await self._client.post(
                    self._url, json=payload, headers=headers, timeout=self._timeout_seconds
                )
            except httpx.TransportError as exc:
                last_reason = self._scrub(str(exc) or type(exc).__name__)
            else:
                status = response.status_code
                if response.is_success:
                    content = self._content(response)
                    log_attempt(
                        self._target,
                        attempt=attempt,
                        max_attempts=attempts,
                        duration_ms=watch.stop(),
                        outcome="ok",
                        status=status,
                        prompt_chars=prompt_chars,
                        response_chars=len(content),
                        usage=usage_from(_json_or_none(response)),
                    )
                    return content
                if not _is_retryable(status):
                    log_attempt(
                        self._target,
                        attempt=attempt,
                        max_attempts=attempts,
                        duration_ms=watch.stop(),
                        outcome="failed",
                        status=status,
                        prompt_chars=prompt_chars,
                    )
                    raise AnalysisError(
                        f"LLM API rejected the request (HTTP {status})",
                        details={"status": status, "reason": self._error(response)},
                    )
                last_reason = f"HTTP {status}: {self._error(response)}"
            final = attempt == self._max_retries
            log_attempt(
                self._target,
                attempt=attempt,
                max_attempts=attempts,
                duration_ms=watch.stop(),
                outcome="failed" if final else "retry",
                status=status,
                prompt_chars=prompt_chars,
                reason=last_reason[:200],
            )
            if not final:
                await self._sleeper(backoff_seconds(self._rng, attempt))

        raise AnalysisError("LLM API request failed after retries", details={"reason": last_reason})

    def _payload(
        self, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> dict[str, object]:
        if self._response_format == "json_schema":
            response_format: dict[str, object] = {
                "type": "json_schema",
                "json_schema": {"name": _SCHEMA_NAME, "schema": schema, "strict": False},
            }
        else:
            # json_object only guarantees valid JSON, so the schema goes in the prompt instead.
            response_format = {"type": "json_object"}
            system_prompt += (
                "\n\nReply with one JSON object that matches this JSON schema:\n"
                + json.dumps(schema)
            )
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": response_format,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "stream": False,
        }

    def _content(self, response: httpx.Response) -> str:
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AnalysisError(
                "LLM API returned an unexpected response shape",
                details={"reason": self._scrub(response.text[:_ERROR_TEXT_LIMIT])},
            ) from exc
        if not isinstance(content, str):
            raise AnalysisError("LLM API returned no message content")
        return content

    def _error(self, response: httpx.Response) -> str:
        return self._scrub(response.text[:_ERROR_TEXT_LIMIT])

    def _scrub(self, text: str) -> str:
        text = scrub_url_credentials(text)
        return text.replace(self._api_key, REDACTED) if self._api_key else text


def _is_retryable(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUS or status_code >= 500


def _json_or_none(response: httpx.Response) -> object:
    try:
        body: object = response.json()
    except ValueError:
        return None
    return body
