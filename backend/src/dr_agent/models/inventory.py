"""System inventory and health-check result models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, Field

from dr_agent.models.base import CamelModel


class InventoryServiceType(StrEnum):
    DATABASE = "database"
    MESSAGING = "messaging"
    SECRETS = "secrets"
    COMPUTE = "compute"
    NETWORK = "network"
    EXTERNAL = "external"


class HealthStatus(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    UNREACHABLE = "UNREACHABLE"


class DependencyStatus(StrEnum):
    """Health as seen from a runbook dependency; adds the not-in-inventory case."""

    UP = "UP"
    DOWN = "DOWN"
    UNREACHABLE = "UNREACHABLE"
    NOT_IN_INVENTORY = "NOT_IN_INVENTORY"


class InventoryService(CamelModel):
    name: str = Field(min_length=1)
    endpoint: AnyHttpUrl
    type: InventoryServiceType
    region: str | None = None
    expected_status: Literal["UP"] = "UP"
    # Mock-only fields (the brief implies a mock status field but omits it from the schema).
    mock_status: HealthStatus = HealthStatus.UP
    mock_latency_ms: float | None = Field(default=None, ge=0)


class SystemInventory(CamelModel):
    services: list[InventoryService] = Field(default_factory=list)


class ServiceStatus(CamelModel):
    """Result of one health check."""

    name: str
    endpoint: str
    status: HealthStatus
    latency_ms: float = Field(ge=0)
    error: str | None = None
