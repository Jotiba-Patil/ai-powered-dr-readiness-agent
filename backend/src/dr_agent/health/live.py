"""LiveHealthChecker: real HTTP checks over an injected httpx.AsyncClient.

The client is injected (never constructed here) so tests can supply an
`httpx.MockTransport` instead of touching the network. A 2xx response is UP, any
other response is DOWN, and a timeout or transport failure is UNREACHABLE.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import httpx

from dr_agent.models.inventory import HealthStatus, InventoryService, ServiceStatus
from dr_agent.utils.timing import Stopwatch


class LiveHealthChecker:
    def __init__(self, client: httpx.AsyncClient, timeout_seconds: float) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def check_all(self, services: Sequence[InventoryService]) -> list[ServiceStatus]:
        results = await asyncio.gather(
            *(self._check_one(service) for service in services), return_exceptions=True
        )
        return [
            result if isinstance(result, ServiceStatus) else self._to_unreachable(service, result)
            for service, result in zip(services, results, strict=True)
        ]

    async def _check_one(self, service: InventoryService) -> ServiceStatus:
        endpoint = str(service.endpoint)
        watch = Stopwatch()
        try:
            response = await self._client.get(endpoint, timeout=self._timeout_seconds)
        except httpx.TimeoutException:
            return ServiceStatus(
                name=service.name,
                endpoint=endpoint,
                status=HealthStatus.UNREACHABLE,
                latency_ms=watch.elapsed_ms,
                error="timed out",
            )
        except httpx.HTTPError as exc:
            return ServiceStatus(
                name=service.name,
                endpoint=endpoint,
                status=HealthStatus.UNREACHABLE,
                latency_ms=watch.elapsed_ms,
                error=str(exc),
            )

        latency_ms = watch.elapsed_ms
        if response.is_success:
            return ServiceStatus(
                name=service.name, endpoint=endpoint, status=HealthStatus.UP, latency_ms=latency_ms
            )
        return ServiceStatus(
            name=service.name,
            endpoint=endpoint,
            status=HealthStatus.DOWN,
            latency_ms=latency_ms,
            error=f"HTTP {response.status_code}",
        )

    def _to_unreachable(self, service: InventoryService, error: BaseException) -> ServiceStatus:
        return ServiceStatus(
            name=service.name,
            endpoint=str(service.endpoint),
            status=HealthStatus.UNREACHABLE,
            latency_ms=0.0,
            error=str(error),
        )
