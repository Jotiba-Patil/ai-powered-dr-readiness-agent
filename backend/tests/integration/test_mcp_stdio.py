"""The mock MCP server as a real subprocess over stdio, as the default mcp-servers.json runs it."""

import json
import random
import sys

from dr_agent.tools.mcp_executor import McpToolExecutor
from dr_agent.tools.servers_config import parse_servers


async def test_stdio_round_trip_keeps_state_for_the_session() -> None:
    config = {
        "drsim": {"transport": "stdio", "command": "${PY}", "args": ["-m", "dr_agent.mock_mcp"]}
    }
    servers = parse_servers(json.dumps(config), {"PY": sys.executable})
    async with McpToolExecutor.from_configs(servers, rng=random.Random(0)) as executor:
        assert len(await executor.list_tools()) == 9
        cold = await executor.call_tool(
            "drsim", "cache_ping", {"cache": "pricing-cache"}, timeout_seconds=30
        )
        assert not cold.ok
        warm = await executor.call_tool(
            "drsim",
            "cache_warm_from_snapshot",
            {"cache": "pricing-cache", "snapshot": "latest"},
            timeout_seconds=30,
        )
        assert warm.ok
        pong = await executor.call_tool(
            "drsim", "cache_ping", {"cache": "pricing-cache"}, timeout_seconds=30
        )
        assert pong.ok  # the same server process kept its state between calls
