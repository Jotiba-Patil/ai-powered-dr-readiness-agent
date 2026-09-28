"""OllamaProvider: calls a local Ollama server's structured-output chat endpoint.

Transport errors (connection failure, timeout, 5xx) are retried with
exponential backoff and jitter; a client is injected so tests never touch the
network. JSON-decode and schema-validation retries are the caller's job
(`llm/parse.py`), since only the caller can rebuild the prompt with a
correction.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

import httpx

from dr_agent.llm.call_log import CallTarget, log_attempt, usage_from
from dr_agent.llm.retry import DEFAULT_MAX_RETRIES, backoff_seconds
from dr_agent.utils.errors import AnalysisError
from dr_agent.utils.logging import scrub_url_credentials
from dr_agent.utils.timing import Clock, Stopwatch

Sleeper = Callable[[float], Awaitable[None]]


class OllamaProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        model: str,
        max_tokens: int,
        rng: random.Random,
        timeout_seconds: float = 300.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Sleeper = asyncio.sleep,
        clock: Clock = time.perf_counter,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._rng = rng
        self._sleeper = sleeper
        self._clock = clock
        self._target = CallTarget("ollama", model, f"{self._base_url}/api/chat")

    async def generate(
        self, *, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_predict": self._max_tokens},
        }

        prompt_chars = len(system_prompt) + len(user_prompt)
        attempts = self._max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            watch = Stopwatch(self._clock)
            status: int | None = None
            try:
                response = await self._client.post(
                    self._target.url, json=payload, timeout=self._timeout_seconds
                )
                status = response.status_code
                response.raise_for_status()
                body = response.json()
                content = str(body["message"]["content"])
            except (httpx.HTTPError, KeyError) as exc:
                last_error = exc
                final = attempt == self._max_retries
                log_attempt(
                    self._target,
                    attempt=attempt,
                    max_attempts=attempts,
                    duration_ms=watch.stop(),
                    outcome="failed" if final else "retry",
                    status=status,
                    prompt_chars=prompt_chars,
                    reason=scrub_url_credentials(str(exc) or type(exc).__name__)[:200],
                )
                if not final:
                    await self._sleeper(backoff_seconds(self._rng, attempt))
            else:
                log_attempt(
                    self._target,
                    attempt=attempt,
                    max_attempts=attempts,
                    duration_ms=watch.stop(),
                    outcome="ok",
                    status=status,
                    prompt_chars=prompt_chars,
                    response_chars=len(content),
                    usage=usage_from(body),
                )
                return content

        raise AnalysisError(
            "Ollama request failed after retries",
            details={"reason": scrub_url_credentials(str(last_error))},
        ) from last_error
