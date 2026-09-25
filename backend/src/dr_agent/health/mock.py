"""MockHealthChecker: reads status straight from the inventory (no network calls).

Simulates the latency and occasional flakiness of a real check so callers exercise
the same async/parallel code paths as `LiveHealthChecker`. The RNG and the sleep
function are both injected so tests are deterministic and fast (no wall-clock sleeps).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence

from dr_agent.models.inventory import HealthStatus, InventoryService, ServiceStatus

Sleeper = Callable[[float], Awaitable[None]]

_DEFAULT_LATENCY_RANGE_MS = (50.0, 200.0)
_DEFAULT_CHAOS_FAILURE_RATE = 0.2


class MockHealthChecker:
    def __init__(
        self,
        rng: random.Random,
        *,
        chaos: bool = False,
        chaos_failure_rate: float = _DEFAULT_CHAOS_FAILURE_RATE,
        latency_range_ms: tuple[float, float] = _DEFAULT_LATENCY_RANGE_MS,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self._rng = rng
        self._chaos = chaos
        self._chaos_failure_rate = chaos_failure_rate
        self._latency_range_ms = latency_range_ms
        self._sleeper = sleeper

    async def check_all(self, services: Sequence[InventoryService]) -> list[ServiceStatus]:
        return list(await asyncio.gather(*(self._check_one(s) for s in services)))

    async def _check_one(self, service: InventoryService) -> ServiceStatus:
        latency_ms = (
            service.mock_latency_ms
            if service.mock_latency_ms is not None
            else self._rng.uniform(*self._latency_range_ms)
        )
        await self._sleeper(latency_ms / 1000)

        if self._chaos and self._rng.random() < self._chaos_failure_rate:
            return ServiceStatus(
                name=service.name,
                endpoint=str(service.endpoint),
                status=HealthStatus.UNREACHABLE,
                latency_ms=latency_ms,
                error="simulated chaos failure",
            )

        status = service.mock_status
        error = None if status is HealthStatus.UP else f"mock status is {status.value}"
        return ServiceStatus(
            name=service.name,
            endpoint=str(service.endpoint),
            status=status,
            latency_ms=latency_ms,
            error=error,
        )
