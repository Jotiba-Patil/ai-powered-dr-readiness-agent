"""`ToolExecutor` protocol plus the tool catalog and result models it speaks.

The engine depends only on this protocol; the dry-run executor, the test fake
and (Phase 10) the MCP SDK client implement it, chosen in `wiring.py`.
Results are untrusted data: they are validated here, truncated, stored and
shown, never fed back into a prompt or used to decide what runs next.
"""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import Field, JsonValue, field_validator

from dr_agent.models.base import CamelModel

MAX_RESULT_CHARS = 16 * 1024
_TRUNCATED = "\n[truncated]"


def _object_schema() -> dict[str, JsonValue]:
    return {"type": "object"}


class ToolSpec(CamelModel):
    """One tool a server offers, as listed by the server (untrusted)."""

    server: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, JsonValue] = Field(default_factory=_object_schema)
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None


class ToolResult(CamelModel):
    """Outcome of one call. `ok=False` is a tool-level failure reported by the server."""

    ok: bool
    content: str = ""
    structured: dict[str, JsonValue] | None = None
    simulated: bool = False

    @field_validator("content")
    @classmethod
    def _truncate_content(cls, value: str) -> str:
        if len(value) <= MAX_RESULT_CHARS:
            return value
        return value[: MAX_RESULT_CHARS - len(_TRUNCATED)] + _TRUNCATED

    @field_validator("structured")
    @classmethod
    def _drop_large_structured(
        cls, value: dict[str, JsonValue] | None
    ) -> dict[str, JsonValue] | None:
        if value is not None and len(json.dumps(value)) > MAX_RESULT_CHARS:
            return {"truncated": True}
        return value


class ToolExecutor(Protocol):
    async def list_tools(self) -> list[ToolSpec]:
        """Every tool every configured server offers (the policy filters them)."""
        ...

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, JsonValue], *, timeout_seconds: float
    ) -> ToolResult:
        """Runs one call. Raises `ToolError` when it could not be completed."""
        ...
