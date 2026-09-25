"""Loads the shipped mock inventories and checks the DOWN/UNREACHABLE ratios
described in docs/IMPLEMENTATION_PLAN.md Phase 3, plus the order-service inventory."""

import json
from pathlib import Path

import pytest

from dr_agent.models.inventory import HealthStatus, SystemInventory

INVENTORIES_DIR = Path(__file__).resolve().parents[3] / "mock-data" / "inventories"


def _load(name: str) -> SystemInventory:
    data = json.loads((INVENTORIES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return SystemInventory.model_validate(data)


def test_healthy_inventory_is_all_up() -> None:
    inv = _load("healthy")
    assert inv.services
    assert all(s.mock_status is HealthStatus.UP for s in inv.services)


def test_partial_outage_has_exactly_two_down() -> None:
    inv = _load("partial-outage")
    statuses = [s.mock_status for s in inv.services]
    assert statuses.count(HealthStatus.DOWN) == 2
    assert statuses.count(HealthStatus.UP) == len(inv.services) - 2


def test_major_outage_has_four_down_and_one_unreachable() -> None:
    inv = _load("major-outage")
    statuses = [s.mock_status for s in inv.services]
    assert statuses.count(HealthStatus.DOWN) == 4
    assert statuses.count(HealthStatus.UNREACHABLE) == 1


@pytest.mark.parametrize("name", ["healthy", "partial-outage", "major-outage"])
def test_all_three_inventories_share_the_same_service_names(name: str) -> None:
    healthy_names = {s.name for s in _load("healthy").services}
    assert {s.name for s in _load(name).services} == healthy_names


@pytest.mark.parametrize("name", ["healthy", "partial-outage", "major-outage"])
def test_card_network_gateway_is_never_listed(name: str) -> None:
    """payment-gateway.md declares this dependency; it must stay unlisted everywhere
    so every inventory demonstrates NOT_IN_INVENTORY for it."""
    assert "card-network-gateway" not in {s.name for s in _load(name).services}


def test_order_service_inventory_covers_every_runbook_dependency() -> None:
    """Pairs with runbooks/order-service.md: every dependency is listed, all UP."""
    from dr_agent.core.parser import parse_runbook

    runbook_md = INVENTORIES_DIR.parent / "runbooks" / "order-service.md"
    runbook = parse_runbook(runbook_md.read_text(encoding="utf-8"))
    inv = _load("order-service")
    assert {s.name for s in inv.services} == {d.name for d in runbook.dependencies}
    assert all(s.mock_status is HealthStatus.UP for s in inv.services)
