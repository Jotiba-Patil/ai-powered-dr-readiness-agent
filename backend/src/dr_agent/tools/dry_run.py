"""Dry-run executor: records what would run and never connects to anything.

It knows the tool catalog it was given (so policy and argument checks still
run against real schemas) and answers every call with a simulated success.
"""

from __future__ import annotations

import json

from pydantic import JsonValue

from dr_agent.tools.base import ToolResult, ToolSpec
from dr_agent.utils.errors import ToolError


class DryRunExecutor:
    def __init__(self, catalog: list[ToolSpec]) -> None:
        self._catalog = list(catalog)
        self._known = {(spec.server, spec.name) for spec in catalog}
        self.calls: list[tuple[str, str, dict[str, JsonValue]]] = []

    async def list_tools(self) -> list[ToolSpec]:
        return list(self._catalog)

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, JsonValue], *, timeout_seconds: float
    ) -> ToolResult:
        if (server, tool) not in self._known:
            raise ToolError(f"dry run: unknown tool {server}/{tool}")
        self.calls.append((server, tool, dict(arguments)))
        rendered = json.dumps(arguments, sort_keys=True)
        return ToolResult(
            ok=True, content=f"dry run: would call {server}/{tool} {rendered}", simulated=True
        )
