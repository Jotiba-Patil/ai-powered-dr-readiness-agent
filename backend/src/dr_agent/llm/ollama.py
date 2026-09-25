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
from collections.abc import Awaitable, Callable

import httpx

from dr_agent.llm.retry import DEFAULT_MAX_RETRIES, backoff_seconds
from dr_agent.utils.errors import AnalysisError
from dr_agent.utils.logging import scrub_url_credentials

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
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._rng = rng
        self._sleeper = sleeper

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

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self._base_url}/api/chat", json=payload, timeout=self._timeout_seconds
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]
                return str(content)
            except (httpx.HTTPError, KeyError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    await self._sleeper(backoff_seconds(self._rng, attempt))

        raise AnalysisError(
            "Ollama request failed after retries",
            details={"reason": scrub_url_credentials(str(last_error))},
        ) from last_error
