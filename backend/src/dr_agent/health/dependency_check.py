"""Cross-matches a runbook's declared dependencies against a health inventory.

Dependency names are matched to inventory service names case-insensitively. A
dependency with no matching inventory entry gets `NOT_IN_INVENTORY` rather than
being checked. `impact` is a deterministic, rule-based description of which
recovery steps mention the dependency (by target system, action text or
validation command) -- the LLM analyzer (Phase 4) may add richer reasoning on
top of this, but the base fact is computed here, not asked of the model.
"""

from __future__ import annotations

from dr_agent.health.base import HealthChecker
from dr_agent.models.inventory import (
    DependencyStatus,
    HealthStatus,
    InventoryService,
    ServiceStatus,
    SystemInventory,
)
from dr_agent.models.report import DependencyHealth
from dr_agent.models.runbook import Dependency, Runbook

_HEALTH_TO_DEPENDENCY_STATUS: dict[HealthStatus, DependencyStatus] = {
    HealthStatus.UP: DependencyStatus.UP,
    HealthStatus.DOWN: DependencyStatus.DOWN,
    HealthStatus.UNREACHABLE: DependencyStatus.UNREACHABLE,
}


async def check_dependencies(
    runbook: Runbook, inventory: SystemInventory, checker: HealthChecker
) -> list[DependencyHealth]:
    services_by_name = {service.name.lower(): service for service in inventory.services}
    matched_services = [
        services_by_name[dep.name.lower()]
        for dep in runbook.dependencies
        if dep.name.lower() in services_by_name
    ]

    statuses_by_name: dict[str, ServiceStatus] = {}
    if matched_services:
        results = await checker.check_all(matched_services)
        statuses_by_name = {result.name.lower(): result for result in results}

    return [
        DependencyHealth(
            name=dep.name,
            actual_status=_status_for(dep, services_by_name, statuses_by_name),
            impact=_impact(dep, runbook),
        )
        for dep in runbook.dependencies
    ]


def _status_for(
    dep: Dependency,
    services_by_name: dict[str, InventoryService],
    statuses_by_name: dict[str, ServiceStatus],
) -> DependencyStatus:
    key = dep.name.lower()
    if key not in services_by_name:
        return DependencyStatus.NOT_IN_INVENTORY
    return _HEALTH_TO_DEPENDENCY_STATUS[statuses_by_name[key].status]


def _impact(dep: Dependency, runbook: Runbook) -> str:
    needle = dep.name.lower()
    affected = [
        step.step_number
        for step in runbook.steps
        if needle in (step.target_system or "").lower()
        or needle in step.action.lower()
        or needle in (step.validation_command or "").lower()
    ]
    if not affected:
        return "not directly referenced by any recovery step"
    joined = ", ".join(str(number) for number in affected)
    return f"referenced by step(s) {joined}"
