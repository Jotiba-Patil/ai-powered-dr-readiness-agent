"""Per-app state shared by the routes, created in the app lifespan."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from dr_agent.api.execution_service import ExecutionService
from dr_agent.api.jobs import JobStore
from dr_agent.config import Settings
from dr_agent.health.base import HealthChecker
from dr_agent.history.service import History
from dr_agent.knowledge.service import KnowledgeBase
from dr_agent.llm.base import LLMProvider


@dataclass(frozen=True)
class AppState:
    settings: Settings
    llm: LLMProvider
    checker: HealthChecker
    jobs: JobStore
    started_at: float
    monotonic: Callable[[], float] = time.monotonic
    execution: ExecutionService | None = None  # None while EXECUTION_ENABLED=false
    history: History | None = None  # None while HISTORY_ENABLED=false
    knowledge: KnowledgeBase | None = None  # None unless history and KNOWLEDGE_ENABLED

    @property
    def uptime_seconds(self) -> float:
        return max(0.0, self.monotonic() - self.started_at)


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "dr", None)
    if not isinstance(state, AppState):
        raise RuntimeError("app state not initialised (lifespan did not run)")
    return state
