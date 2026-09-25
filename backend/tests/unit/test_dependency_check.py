import random
from collections.abc import Sequence

from dr_agent.health.dependency_check import check_dependencies
from dr_agent.health.mock import MockHealthChecker
from dr_agent.models.inventory import (
    DependencyStatus,
    InventoryService,
    ServiceStatus,
    SystemInventory,
)
from dr_agent.models.runbook import Dependency, Runbook, Step


async def _noop_sleep(_seconds: float) -> None:
    return None


def _inventory(**statuses: str) -> SystemInventory:
    return SystemInventory.model_validate(
        {
            "services": [
                {
                    "name": name,
                    "endpoint": f"https://health.internal/{name}",
                    "type": "database",
                    "mockStatus": status,
                }
                for name, status in statuses.items()
            ]
        }
    )


def _runbook(dependency_names: list[str], steps: list[Step] | None = None) -> Runbook:
    return Runbook(
        service_name="Svc",
        system_owner="Dana",
        rto_minutes=60,
        rpo_minutes=15,
        raw_markdown="# Svc",
        dependencies=[Dependency(name=name) for name in dependency_names],
        steps=steps or [Step(step_number=1, action="Do it", owner="Dana", estimated_minutes=5)],
    )


async def test_dependency_present_and_up() -> None:
    runbook = _runbook(["estimate-postgres"])
    inventory = _inventory(**{"estimate-postgres": "UP"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].actual_status is DependencyStatus.UP


async def test_dependency_present_and_down() -> None:
    runbook = _runbook(["payment-ledger-db"])
    inventory = _inventory(**{"payment-ledger-db": "DOWN"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].actual_status is DependencyStatus.DOWN


async def test_dependency_present_and_unreachable() -> None:
    runbook = _runbook(["legacy-token-vault"])
    inventory = _inventory(**{"legacy-token-vault": "UNREACHABLE"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].actual_status is DependencyStatus.UNREACHABLE


async def test_dependency_not_in_inventory() -> None:
    runbook = _runbook(["card-network-gateway"])
    inventory = _inventory(**{"estimate-postgres": "UP"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].actual_status is DependencyStatus.NOT_IN_INVENTORY


async def test_matching_is_case_insensitive() -> None:
    runbook = _runbook(["Estimate-Postgres"])
    inventory = _inventory(**{"estimate-postgres": "UP"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].actual_status is DependencyStatus.UP


async def test_empty_dependencies_returns_empty_list_without_calling_checker() -> None:
    runbook = _runbook([])
    inventory = _inventory(**{"estimate-postgres": "UP"})

    class ExplodingChecker:
        async def check_all(self, services: Sequence[InventoryService]) -> list[ServiceStatus]:
            raise AssertionError("should not be called when there are no dependencies to check")

    results = await check_dependencies(runbook, inventory, ExplodingChecker())
    assert results == []


async def test_impact_names_the_referencing_steps() -> None:
    steps = [
        Step(
            step_number=1,
            action="Reconnect estimate-postgres",
            owner="Dana",
            estimated_minutes=5,
        ),
        Step(step_number=2, action="Notify support", owner="Dana", estimated_minutes=5),
    ]
    runbook = _runbook(["estimate-postgres"], steps=steps)
    inventory = _inventory(**{"estimate-postgres": "UP"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].impact == "referenced by step(s) 1"


async def test_impact_defaults_when_no_step_references_dependency() -> None:
    runbook = _runbook(["estimate-postgres"])
    inventory = _inventory(**{"estimate-postgres": "UP"})
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)

    results = await check_dependencies(runbook, inventory, checker)

    assert results[0].impact == "not directly referenced by any recovery step"
