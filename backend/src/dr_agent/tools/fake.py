"""FakeExecutor: a scripted, in-memory `ToolExecutor` for tests and demos.

Each `(server, tool)` has a queue of outcomes (a `ToolResult` or an exception
to raise); once a queue is empty the default is a plain success. An optional
`gate` lets a test hold a call open to exercise abort and restart paths.
"""

from __future__ import annotations

import asyncio

from pydantic import JsonValue

from dr_agent.tools.base import ToolResult, ToolSpec

Outcome = ToolResult | Exception


class FakeExecutor:
    def __init__(self, catalog: list[ToolSpec], *, gate: asyncio.Event | None = None) -> None:
        self._catalog = list(catalog)
        self._scripts: dict[tuple[str, str], list[Outcome]] = {}
        self.gate = gate
        self.started = asyncio.Event()
        self.calls: list[tuple[str, str, dict[str, JsonValue]]] = []

    def script(self, server: str, tool: str, *outcomes: Outcome) -> None:
        self._scripts.setdefault((server, tool), []).extend(outcomes)

    async def list_tools(self) -> list[ToolSpec]:
        return list(self._catalog)

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, JsonValue], *, timeout_seconds: float
    ) -> ToolResult:
        self.calls.append((server, tool, dict(arguments)))
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        queue = self._scripts.get((server, tool), [])
        outcome: Outcome = queue.pop(0) if queue else ToolResult(ok=True, content="ok")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
