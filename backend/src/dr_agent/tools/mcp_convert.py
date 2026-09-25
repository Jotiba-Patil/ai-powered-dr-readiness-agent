"""Converts between the MCP SDK and our tool models; builds SDK clients from config.

Everything that comes back from a server (tool names, descriptions, schemas,
results) is untrusted: it is validated into `ToolSpec` / `ToolResult` here,
descriptions are shortened and results truncated (`ToolResult`).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent, Tool
from pydantic import ValidationError as PydanticValidationError

from dr_agent.tools.base import ToolResult, ToolSpec
from dr_agent.tools.servers_config import HttpServerConfig, StdioServerConfig
from dr_agent.utils.errors import ToolError

ClientFactory = Callable[[], Client]
_MAX_DESCRIPTION = 1000


def client_factory(config: StdioServerConfig | HttpServerConfig) -> ClientFactory:
    """A fresh `Client` per connection attempt (transports are single-use)."""
    if isinstance(config, StdioServerConfig):
        params = StdioServerParameters(
            command=config.command,
            args=list(config.args),
            env={k: v.get_secret_value() for k, v in config.env.items()} or None,
            cwd=config.cwd,
        )
        return lambda: Client(params)
    url = config.url
    if not config.headers:
        return lambda: Client(url)
    headers = {k: v.get_secret_value() for k, v in config.headers.items()}
    return lambda: Client(
        streamable_http_client(url, http_client=httpx2.AsyncClient(headers=headers))
    )


def to_tool_spec(server: str, tool: Tool) -> ToolSpec:
    annotations = tool.annotations
    try:
        return ToolSpec.model_validate(
            {
                "server": server,
                "name": tool.name,
                "description": (tool.description or "")[:_MAX_DESCRIPTION],
                "input_schema": tool.input_schema,
                "read_only_hint": annotations.read_only_hint if annotations else None,
                "destructive_hint": annotations.destructive_hint if annotations else None,
            }
        )
    except PydanticValidationError as exc:
        raise ToolError(
            f"MCP server {server} listed an invalid tool", details={"tool": tool.name[:128]}
        ) from exc


def to_tool_result(result: CallToolResult) -> ToolResult:
    texts = [
        block.text if isinstance(block, TextContent) else f"[{block.type} content omitted]"
        for block in result.content
    ]
    structured = result.structured_content if isinstance(result.structured_content, dict) else None
    try:
        return ToolResult.model_validate(
            {"ok": not result.is_error, "content": "\n".join(texts), "structured": structured}
        )
    except PydanticValidationError as exc:
        raise ToolError("the MCP server returned a result that is not valid JSON data") from exc
