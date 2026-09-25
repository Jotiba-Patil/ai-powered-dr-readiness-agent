"""Per-execution unit of work: lock, load, mutate through a `Journal`, save.

Nothing is saved when the body raises, so a refused request changes nothing.
Locks are per execution id and never held while a tool call is in flight.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from dr_agent.config import Settings
from dr_agent.execution.journal import Journal
from dr_agent.execution.store import ExecutionStore


@dataclass(frozen=True)
class ExecutionLimits:
    """Safety limits (ADR 0006); the defaults match the settings' defaults."""

    enabled: bool = False
    allow_live: bool = False
    approval_timeout: timedelta = timedelta(minutes=30)
    tool_timeout_seconds: float = 120.0
    max_tool_calls: int = 50
    max_active: int = 3

    @classmethod
    def from_settings(cls, settings: Settings) -> ExecutionLimits:
        return cls(
            enabled=settings.execution_enabled,
            allow_live=settings.execution_allow_live,
            approval_timeout=timedelta(minutes=settings.execution_approval_timeout_minutes),
            tool_timeout_seconds=settings.execution_tool_timeout_seconds,
            max_tool_calls=settings.execution_max_tool_calls,
            max_active=settings.execution_max_active,
        )


class Sessions:
    def __init__(self, store: ExecutionStore, clock: Callable[[], datetime]) -> None:
        self.store = store
        self.clock = clock
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def open(self, execution_id: str) -> AsyncIterator[Journal]:
        lock = self._locks.setdefault(execution_id, asyncio.Lock())
        async with lock:
            execution = await self.store.get(execution_id)
            journal = Journal(execution, self.clock())
            yield journal
            if journal.events:
                await self.store.save(execution, journal.events)
