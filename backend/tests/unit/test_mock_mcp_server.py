"""The drsim MCP server through the real MCP client (SDK in-memory transport)."""

import random
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from exec_support import DRSIM
from mcp import Client

from dr_agent.mock_mcp import __main__ as mock_main
from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.mock_mcp.state import Scenario, ToolFault
from dr_agent.tools.mcp_executor import McpToolExecutor

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
async def connected() -> AsyncIterator[tuple[McpToolExecutor, DrEnvironment]]:
    env = DrEnvironment(Scenario(faults={"smoke_run": ToolFault(fail_on_calls=[1], message="red")}))
    server = build_server(env)
    async with McpToolExecutor({"drsim": lambda: Client(server)}, rng=random.Random(0)) as ex:
        yield ex, env


async def test_lists_the_nine_tools_with_schemas_and_hints(
    connected: tuple[McpToolExecutor, DrEnvironment],
) -> None:
    executor, _ = connected
    specs = {spec.name: spec for spec in await executor.list_tools()}
    assert set(specs) == set(DRSIM)
    for name, (required, optional, read_only, destructive, _risk) in DRSIM.items():
        spec = specs[name]
        assert spec.server == "drsim"
        assert spec.description
        assert sorted(spec.input_schema["required"]) == sorted(required)  # type: ignore[arg-type]  # JSON schema list
        properties = spec.input_schema["properties"]
        assert isinstance(properties, dict)
        assert set(properties) == set(required) | set(optional)
        assert (spec.read_only_hint, spec.destructive_hint) == (read_only, destructive)
    assert (await executor.refresh()) == list(specs.values())


async def test_calls_change_the_environment_and_return_structured_results(
    connected: tuple[McpToolExecutor, DrEnvironment],
) -> None:
    executor, env = connected
    result = await executor.call_tool(
        "drsim",
        "k8s_rollout_restart",
        {"deployment": "estimate-service", "region": "standby"},
        timeout_seconds=5,
    )
    assert result.ok
    assert result.structured is not None
    assert result.structured["ready"] is True
    assert '"revision": 8' in result.content
    assert env.state.deployments["estimate-service"]["standby"].ready


async def test_tool_failures_and_bad_arguments_are_error_results(
    connected: tuple[McpToolExecutor, DrEnvironment],
) -> None:
    executor, _ = connected
    injected = await executor.call_tool(
        "drsim",
        "smoke_run",
        {"service": "estimate-service", "region": "standby"},
        timeout_seconds=5,
    )
    assert (injected.ok, injected.content) == (False, "Error executing tool smoke_run: red")
    real = await executor.call_tool(
        "drsim", "cache_ping", {"cache": "pricing-cache"}, timeout_seconds=5
    )
    assert not real.ok
    assert "cold" in real.content
    bad = await executor.call_tool(
        "drsim", "dns_switch_region", {"service": "x", "region": "mars"}, timeout_seconds=5
    )
    assert not bad.ok
    unknown = await executor.call_tool("drsim", "rm_rf", {}, timeout_seconds=5)
    assert not unknown.ok


def test_main_runs_the_chosen_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runs: list[tuple[str, dict[str, object]]] = []

    def fake_run(self: object, transport: str = "stdio", **kwargs: object) -> None:
        runs.append((transport, kwargs))

    monkeypatch.setattr("mcp.server.mcpserver.MCPServer.run", fake_run)
    assert mock_main.main([]) == 0
    assert mock_main.main(["--transport", "http", "--host", "10.0.0.5", "--port", "9000"]) == 0
    assert mock_main.main(["--transport", "http", "--allowed-host", "mock-mcp:*"]) == 0
    assert runs[0] == ("stdio", {})
    assert runs[1] == (
        "streamable-http",
        {"host": "10.0.0.5", "port": 9000, "transport_security": None},
    )
    security = runs[2][1]["transport_security"]
    assert security is not None
    assert security.allowed_hosts == ["mock-mcp:*"]  # type: ignore[attr-defined]  # settings model
    scenario = tmp_path / "s.json"
    scenario.write_text('{"faults": {}}', encoding="utf-8")
    assert mock_main.main(["--scenario", str(scenario)]) == 0
    assert mock_main.main(["--scenario", str(tmp_path / "missing.json")]) == 1
