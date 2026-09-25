"""Table-driven tests over the mock runbooks that ship with the project."""

from pathlib import Path

import pytest

from dr_agent.core.parser import parse_runbook
from dr_agent.models.runbook import Runbook

REPO_ROOT = Path(__file__).resolve().parents[3]
MOCK_RUNBOOKS_DIR = REPO_ROOT / "mock-data" / "runbooks"


def _load(name: str) -> Runbook:
    return parse_runbook((MOCK_RUNBOOKS_DIR / name).read_text(encoding="utf-8"))


def test_estimate_service_is_a_clean_happy_path() -> None:
    rb = _load("estimate-service.md")
    assert rb.service_name == "Estimate Service"
    assert rb.system_owner == "Alice Chen"
    assert rb.rto_minutes == 60
    assert len(rb.steps) == 5
    assert len(rb.dependencies) == 4
    assert rb.parser_warnings == []
    total_minutes = sum(step.estimated_minutes for step in rb.steps)
    assert total_minutes < rb.rto_minutes
    assert all(step.owner != "Unspecified" for step in rb.steps)
    assert all(step.validation_command for step in rb.steps)


def test_payment_gateway_has_vague_and_ambiguous_owners() -> None:
    rb = _load("payment-gateway.md")
    assert rb.system_owner == "team"
    assert rb.rto_minutes == 30
    ambiguous = [step for step in rb.steps if step.owner == "team"]
    assert len(ambiguous) == 2
    assert all(step.validation_command is None for step in rb.steps)
    total_minutes = sum(step.estimated_minutes for step in rb.steps)
    assert total_minutes == 45
    assert total_minutes > rb.rto_minutes
    assert any("range" in w for w in rb.parser_warnings)


def test_auth_service_has_bus_factor_one_and_infeasible_rto() -> None:
    rb = _load("auth-service.md")
    owners = {step.owner for step in rb.steps}
    assert owners == {"Frank Osei"}
    assert rb.dependencies == []
    total_minutes = sum(step.estimated_minutes for step in rb.steps)
    assert total_minutes > rb.rto_minutes
    assert "no dependencies found in the Dependencies section" in rb.parser_warnings


def test_order_service_extracts_every_field_without_warnings() -> None:
    rb = _load("order-service.md")
    assert (rb.service_name, rb.system_owner) == ("Order Service", "Maria Lopez")
    assert (rb.rto_minutes, rb.rpo_minutes) == (60, 5)
    assert rb.parser_warnings == []
    assert len(rb.dependencies) == 7
    assert {d.type.value for d in rb.dependencies} == {
        "database",
        "messaging",
        "secrets",
        "external",
        "compute",
        "network",
    }
    assert [d.name for d in rb.dependencies if not d.critical] == ["orders-redis"]
    assert len(rb.steps) == 8
    assert all(s.owner != "Unspecified" and s.target_system for s in rb.steps)
    assert all((s.validation_command or "").startswith("curl -sf https://") for s in rb.steps)
    assert sum(s.estimated_minutes for s in rb.steps) == 48
    depends = {s.step_number: s.depends_on for s in rb.steps}
    assert depends[6] == [2, 3, 4]
    assert depends[8] == [5, 7]


@pytest.mark.parametrize(
    "name", ["estimate-service.md", "payment-gateway.md", "auth-service.md", "order-service.md"]
)
def test_all_mock_runbooks_parse_without_raising(name: str) -> None:
    rb = _load(name)
    assert rb.steps
    assert rb.raw_markdown
