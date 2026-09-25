"""McpToolExecutor: connect/list retries, no call retries, error wrapping, conversions."""

import random

import pytest
from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, Tool

from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.tools.mcp_convert import client_factory, to_tool_result, to_tool_spec
from dr_agent.tools.mcp_executor import McpToolExecutor
from dr_agent.tools.servers_config import HttpServerConfig, StdioServerConfig
from dr_agent.utils.errors import ToolError


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


async def test_connecting_is_retried_with_backoff() -> None:
    server = build_server(DrEnvironment())
    attempts: list[int] = []

    def flaky() -> Client:
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionRefusedError("not yet")
        return Client(server)

    sleeps = Sleeps()
    async with McpToolExecutor({"drsim": flaky}, rng=random.Random(0), sleep=sleeps) as ex:
        assert len(await ex.list_tools()) == 9
    assert len(attempts) == 3
    assert len(sleeps.delays) == 2
    assert sleeps.delays[0] < sleeps.delays[1]


async def test_giving_up_raises_a_tool_error_without_details_of_the_target() -> None:
    def refused() -> Client:
        raise ConnectionRefusedError("http://user:secret@host/mcp")

    executor = McpToolExecutor({"drsim": refused}, rng=random.Random(0), sleep=Sleeps())
    with pytest.raises(ToolError) as info:
        async with executor:
            pass  # pragma: no cover - never reached
    assert info.value.message == "cannot connect on MCP server 'drsim' (ConnectionRefusedError)"
    assert info.value.details == {"server": "drsim", "attempts": 3}
    assert "secret" not in str(info.value.to_dict())


async def test_calls_are_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def broken(self: Client, name: str, *args: object, **kwargs: object) -> CallToolResult:
        calls.append(name)
        raise OSError("pipe closed")

    server = build_server(DrEnvironment())
    async with McpToolExecutor({"drsim": lambda: Client(server)}, rng=random.Random(0)) as ex:
        monkeypatch.setattr(Client, "call_tool", broken)
        with pytest.raises(
            ToolError, match="did not complete \\(OSError\\); its outcome is unknown"
        ):
            await ex.call_tool("drsim", "smoke_run", {}, timeout_seconds=1)
        with pytest.raises(ToolError, match="'nope' is not connected"):
            await ex.call_tool("nope", "smoke_run", {}, timeout_seconds=1)
    assert calls == ["smoke_run"]


async def test_leaving_twice_and_before_entering_is_harmless() -> None:
    executor = McpToolExecutor({}, rng=random.Random(0))
    await executor.__aexit__(None, None, None)
    async with executor as ex:
        assert await ex.list_tools() == []


def test_client_factories_from_config() -> None:
    stdio = client_factory(
        StdioServerConfig.model_validate(
            {"transport": "stdio", "command": "python", "args": ["-m", "x"], "env": {"A": "1"}}
        )
    )()
    assert isinstance(stdio.server, StdioServerParameters)
    assert (stdio.server.command, stdio.server.args, stdio.server.env) == (
        "python",
        ["-m", "x"],
        {"A": "1"},
    )
    plain = client_factory(HttpServerConfig(transport="http", url="http://mock-mcp:8765/mcp"))()
    assert plain.server == "http://mock-mcp:8765/mcp"
    with_headers = client_factory(
        HttpServerConfig.model_validate(
            {"transport": "http", "url": "https://x/mcp", "headers": {"Authorization": "t"}}
        )
    )()
    assert not isinstance(with_headers.server, str)


def test_result_conversion() -> None:
    result = CallToolResult.model_validate(
        {
            "content": [
                {"type": "text", "text": "done"},
                {"type": "image", "data": "aGk=", "mimeType": "image/png"},
            ],
            "structuredContent": {"a": 1},
            "isError": False,
        }
    )
    converted = to_tool_result(result)
    assert converted.ok
    assert converted.content == "done\n[image content omitted]"
    assert converted.structured == {"a": 1}


def test_invalid_tool_listing_is_rejected() -> None:
    tool = Tool.model_validate({"name": "", "inputSchema": {"type": "object"}})
    with pytest.raises(ToolError, match="listed an invalid tool"):
        to_tool_spec("drsim", tool)
    long = Tool.model_validate(
        {"name": "t", "description": "d" * 5000, "inputSchema": {"type": "object"}}
    )
    spec = to_tool_spec("drsim", long)
    assert len(spec.description) == 1000
    assert spec.read_only_hint is None
