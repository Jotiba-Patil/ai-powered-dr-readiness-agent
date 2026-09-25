"""HealthChecker: the injectable strategy interface for checking service health."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from dr_agent.models.inventory import InventoryService, ServiceStatus


class HealthChecker(Protocol):
    """Checks a batch of inventory services in parallel and returns one status each,
    in the same order as `services`."""

    async def check_all(self, services: Sequence[InventoryService]) -> list[ServiceStatus]: ...
