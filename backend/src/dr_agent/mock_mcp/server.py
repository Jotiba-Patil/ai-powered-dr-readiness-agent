"""The `drsim` MCP server: nine DR tools over one `DrEnvironment` (ADR 0005).

Tools declare MCP annotations (`readOnlyHint`, `destructiveHint`,
`idempotentHint`); the execution policy may use them only to raise a risk
class. Anticipated failures become MCP tool errors with a readable message.
"""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from dr_agent.mock_mcp.environment import DrEnvironment, Result, SimulatedFailureError
from dr_agent.mock_mcp.state import Region

SERVER_NAME = "drsim"
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)


def build_server(env: DrEnvironment) -> MCPServer:
    server = MCPServer(SERVER_NAME, instructions="Simulated DR environment for drills and tests.")

    async def run(tool: str, operation: Callable[[], Result]) -> Result:
        try:
            await env.enter(tool)
            return operation()
        except SimulatedFailureError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=READ)
    async def k8s_rollout_status(
        deployment: str, region: Region, expect_ready: bool | None = None
    ) -> Result:
        """Deployment revision and readiness in a region; fails if `expect_ready` is not met."""
        return await run(
            "k8s_rollout_status", lambda: env.rollout_status(deployment, region, expect_ready)
        )

    @server.tool(annotations=WRITE)
    async def k8s_rollout_restart(deployment: str, region: Region) -> Result:
        """Restarts a deployment in a region (new revision, becomes ready)."""
        return await run("k8s_rollout_restart", lambda: env.rollout_restart(deployment, region))

    @server.tool(annotations=WRITE)
    async def k8s_rollout_undo(deployment: str, region: Region) -> Result:
        """Rolls a deployment back to the revision before its last restart."""
        return await run("k8s_rollout_undo", lambda: env.rollout_undo(deployment, region))

    @server.tool(annotations=READ)
    async def db_is_in_recovery(cluster: str, expect_in_recovery: bool | None = None) -> Result:
        """Whether the database is a replica in recovery; fails if the expectation is not met."""
        return await run(
            "db_is_in_recovery", lambda: env.db_is_in_recovery(cluster, expect_in_recovery)
        )

    @server.tool(annotations=DESTRUCTIVE)
    async def db_promote_replica(cluster: str) -> Result:
        """Promotes the standby replica to primary. Cannot be undone."""
        return await run("db_promote_replica", lambda: env.db_promote_replica(cluster))

    @server.tool(annotations=READ)
    async def cache_ping(cache: str) -> Result:
        """Pings a cache; fails while it is cold."""
        return await run("cache_ping", lambda: env.cache_ping(cache))

    @server.tool(annotations=WRITE)
    async def cache_warm_from_snapshot(cache: str, snapshot: str) -> Result:
        """Loads a cache from a named snapshot (`latest` by default)."""
        return await run("cache_warm_from_snapshot", lambda: env.cache_warm(cache, snapshot))

    @server.tool(annotations=DESTRUCTIVE)
    async def dns_switch_region(service: str, region: Region) -> Result:
        """Points the service's DNS record at a region."""
        return await run("dns_switch_region", lambda: env.dns_switch(service, region))

    @server.tool(annotations=READ)
    async def smoke_run(service: str, region: Region) -> Result:
        """Runs the smoke checks for a service in a region; fails listing the failed checks."""
        return await run("smoke_run", lambda: env.smoke_run(service, region))

    return server
