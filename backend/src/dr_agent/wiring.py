"""Composition root: builds the injected providers from validated `Settings`.

This is the only place that picks concrete `LLMProvider` / `HealthChecker`
implementations, so swapping to a real integration (another LLM backend, live
health checks) means changing config or this file, never `core/` or `health/`.
"""

from __future__ import annotations

import random

import httpx

from dr_agent.config import Settings
from dr_agent.health.base import HealthChecker
from dr_agent.health.live import LiveHealthChecker
from dr_agent.health.mock import MockHealthChecker
from dr_agent.llm.base import LLMProvider
from dr_agent.llm.disabled import DisabledProvider
from dr_agent.llm.ollama import OllamaProvider
from dr_agent.llm.openai_compatible import OpenAICompatibleProvider


def build_llm(settings: Settings, client: httpx.AsyncClient, rng: random.Random) -> LLMProvider:
    if settings.llm_provider == "none":
        return DisabledProvider()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(
            client,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            rng=rng,
            api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
            response_format=settings.llm_response_format,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return OllamaProvider(
        client,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        rng=rng,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def build_checker(
    settings: Settings,
    client: httpx.AsyncClient,
    rng: random.Random,
    *,
    chaos: bool | None = None,
) -> HealthChecker:
    """`chaos` overrides `HEALTH_CHECK_CHAOS` when given (the CLI's `--chaos` flag)."""
    if settings.health_checker == "live":
        return LiveHealthChecker(client, timeout_seconds=settings.health_check_timeout_ms / 1000)
    return MockHealthChecker(rng, chaos=settings.health_check_chaos if chaos is None else chaos)
