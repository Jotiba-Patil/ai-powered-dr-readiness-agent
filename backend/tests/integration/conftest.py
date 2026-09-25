"""Shared fixtures for API and CLI integration tests (no real LLM, no network, no sleeps)."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dr_agent.api.app import create_app
from dr_agent.config import Settings
from dr_agent.health.mock import MockHealthChecker
from dr_agent.llm.base import LLMProvider
from dr_agent.llm.fake import FakeProvider

REPO = Path(__file__).resolve().parents[3]
MOCK = REPO / "mock-data"

ClientFactory = Callable[..., TestClient]


def llm_json(risk_score: int = 42) -> str:
    return json.dumps(
        {
            "stepDependencies": [{"stepNumber": 2, "dependsOn": [1]}],
            "singlePointsOfFailure": [],
            "gapAnalysis": [],
            "suggestions": [{"priority": 1, "title": "Rehearse", "detail": "Quarterly drill"}],
            "summary": "Grounded executive summary.",
            "riskScore": risk_score,
        }
    )


def fake_llm(risk_score: int = 42, calls: int = 10) -> FakeProvider:
    return FakeProvider([llm_json(risk_score)] * calls)


class BlockingProvider:
    """Never answers: keeps a job RUNNING until it is cancelled."""

    async def generate(
        self, *, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> str:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def no_sleep(_seconds: float) -> None:
    return None


def mock_checker() -> MockHealthChecker:
    return MockHealthChecker(random.Random(42), sleeper=no_sleep)


def read_mock(relative: str) -> bytes:
    return (MOCK / relative).read_bytes()


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    """Build a TestClient (lifespan running) with injected fakes and settings overrides."""
    clients: list[TestClient] = []

    def factory(
        llm: LLMProvider | None = None,
        *,
        raise_server_exceptions: bool = True,
        **overrides: object,
    ) -> TestClient:
        values: dict[str, object] = {
            "llm_provider": "none",
            "api_allowed_dir": str(MOCK),
            "api_max_upload_bytes": 64 * 1024,
            "api_wait_timeout_seconds": 5.0,
            **overrides,
        }
        settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
        app = create_app(
            settings, llm=llm or fake_llm(), checker=mock_checker(), monotonic=lambda: 100.0
        )
        client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)
