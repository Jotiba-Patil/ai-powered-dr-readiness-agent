"""The simulated DR environment behind the mock MCP server's nine tools.

Each operation checks and changes `EnvironmentState` and returns a JSON-ready
dict. Expected failures raise `SimulatedFailureError`, which the server turns into
an MCP tool error (`isError: true` with the message). Faults from the scenario
and an optional `before_call` hook (tests use it to hold a call in flight) are
applied before every operation. It models only what the sample runbooks need.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

from dr_agent.mock_mcp.state import (
    CacheState,
    DatabaseState,
    DeploymentState,
    EnvironmentState,
    Region,
    Scenario,
    ToolFault,
)

Result = dict[str, object]


class SimulatedFailureError(Exception):
    """An anticipated tool failure; its message is shown to the caller."""


class DrEnvironment:
    def __init__(self, scenario: Scenario | None = None) -> None:
        scenario = scenario or Scenario()
        self.state: EnvironmentState = scenario.state.model_copy(deep=True)
        self.faults: dict[str, ToolFault] = dict(scenario.faults)
        self.call_counts: Counter[str] = Counter()
        self.before_call: Callable[[str], Awaitable[None]] | None = None

    async def enter(self, tool: str) -> None:
        """Counts the call and applies the hook and any fault configured for the tool."""
        self.call_counts[tool] += 1
        if self.before_call is not None:
            await self.before_call(tool)
        fault = self.faults.get(tool)
        if fault is None:
            return
        if fault.latency_ms:
            await asyncio.sleep(fault.latency_ms / 1000)
        if fault.fails(self.call_counts[tool]):
            raise SimulatedFailureError(fault.message)

    def rollout_status(self, deployment: str, region: Region, expect_ready: bool | None) -> Result:
        state = self._deployment(deployment, region)
        if expect_ready is not None and state.ready != expect_ready:
            raise SimulatedFailureError(
                f"{deployment} in {region}: expected ready={expect_ready}, found {_replicas(state)}"
            )
        return {"deployment": deployment, "region": region} | _describe(state)

    def rollout_restart(self, deployment: str, region: Region) -> Result:
        state = self._deployment(deployment, region)
        state.previous = (state.revision, state.ready)
        state.revision += 1
        state.ready = True
        return {"deployment": deployment, "region": region} | _describe(state)

    def rollout_undo(self, deployment: str, region: Region) -> Result:
        state = self._deployment(deployment, region)
        if state.previous is None:
            raise SimulatedFailureError(
                f"{deployment} in {region}: no previous revision to undo to"
            )
        (state.revision, state.ready), state.previous = state.previous, None
        return {"deployment": deployment, "region": region} | _describe(state)

    def db_is_in_recovery(self, cluster: str, expect_in_recovery: bool | None) -> Result:
        in_recovery = not self._database(cluster).primary
        if expect_in_recovery is not None and in_recovery != expect_in_recovery:
            raise SimulatedFailureError(
                f"{cluster}: expected in_recovery={expect_in_recovery}, found {in_recovery}"
            )
        return {"cluster": cluster, "inRecovery": in_recovery}

    def db_promote_replica(self, cluster: str) -> Result:
        database = self._database(cluster)
        if database.primary:
            raise SimulatedFailureError(f"{cluster} is already the primary")
        database.primary = True
        return {"cluster": cluster, "promoted": True, "inRecovery": False}

    def cache_ping(self, cache: str) -> Result:
        if not self._cache(cache).warm:
            raise SimulatedFailureError(f"{cache} is reachable but cold (no keys loaded)")
        return {"cache": cache, "pong": True, "warm": True}

    def cache_warm(self, cache: str, snapshot: str) -> Result:
        state = self._cache(cache)
        if snapshot not in state.snapshots:
            raise SimulatedFailureError(f"{cache}: unknown snapshot '{snapshot}'")
        state.warm = True
        return {"cache": cache, "snapshot": snapshot, "warm": True}

    def dns_switch(self, service: str, region: Region) -> Result:
        if service not in self.state.dns:
            raise SimulatedFailureError(f"unknown DNS record for service '{service}'")
        previous = self.state.dns[service]
        self.state.dns[service] = region
        return {"service": service, "region": region, "previous": previous}

    def smoke_run(self, service: str, region: Region) -> Result:
        checks = {
            "dnsPointsToRegion": self.state.dns.get(service) == region,
            "deploymentReady": self._deployment(service, region).ready,
            "databasesPrimary": all(db.primary for db in self.state.databases.values()),
            "cachesWarm": all(cache.warm for cache in self.state.caches.values()),
        }
        failed = sorted(name for name, ok in checks.items() if not ok)
        if failed:
            raise SimulatedFailureError(f"smoke tests failed in {region}: {', '.join(failed)}")
        return {"service": service, "region": region, "passed": True, "checks": dict(checks)}

    def _deployment(self, name: str, region: Region) -> DeploymentState:
        regions = self.state.deployments.get(name)
        if regions is None or region not in regions:
            raise SimulatedFailureError(f"unknown deployment '{name}' in {region}")
        return regions[region]

    def _database(self, cluster: str) -> DatabaseState:
        if cluster not in self.state.databases:
            raise SimulatedFailureError(f"unknown database cluster '{cluster}'")
        return self.state.databases[cluster]

    def _cache(self, cache: str) -> CacheState:
        if cache not in self.state.caches:
            raise SimulatedFailureError(f"unknown cache '{cache}'")
        return self.state.caches[cache]


def _describe(state: DeploymentState) -> Result:
    return {"revision": state.revision, "ready": state.ready, "replicas": _replicas(state)}


def _replicas(state: DeploymentState) -> str:
    return "3/3 ready" if state.ready else "0/3 ready"
