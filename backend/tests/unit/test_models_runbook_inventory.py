import pytest
from pydantic import ValidationError

from dr_agent.models import (
    Dependency,
    DependencyType,
    HealthStatus,
    InventoryService,
    Runbook,
    ServiceStatus,
    Step,
    SystemInventory,
)


def make_runbook(**overrides: object) -> Runbook:
    data: dict[str, object] = {
        "serviceName": "Estimate Service",
        "systemOwner": "Dana",
        "rtoMinutes": 60,
        "rpoMinutes": 15,
        "rawMarkdown": "# Estimate Service",
        "steps": [
            {"stepNumber": 1, "action": "Restore DB", "owner": "Dana", "estimatedMinutes": 10},
            {
                "stepNumber": 2,
                "action": "Start app",
                "owner": "Sam",
                "estimatedMinutes": 5,
                "dependsOn": [1],
            },
        ],
    }
    data.update(overrides)
    return Runbook.model_validate(data)


def test_runbook_parses_camel_case_and_defaults() -> None:
    rb = make_runbook()
    assert rb.service_name == "Estimate Service"
    assert rb.dependencies == []
    assert rb.parser_warnings == []
    assert rb.steps[0].depends_on == []
    assert rb.steps[0].target_system is None
    assert rb.steps[1].depends_on == [1]


def test_runbook_accepts_snake_case_and_serializes_camel_case() -> None:
    rb = Runbook(
        service_name="X",
        system_owner="Y",
        rto_minutes=30,
        rpo_minutes=5,
        raw_markdown="# X",
        dependencies=[Dependency(name="pg", type=DependencyType.DATABASE, critical=True)],
    )
    dumped = rb.to_json_dict()
    assert dumped["serviceName"] == "X"
    assert dumped["rtoMinutes"] == 30
    assert dumped["parserWarnings"] == []
    assert dumped["dependencies"] == [{"name": "pg", "type": "database", "critical": True}]
    assert Runbook.model_validate(dumped) == rb


def test_dependency_defaults() -> None:
    dep = Dependency(name="Vault")
    assert dep.type is DependencyType.OTHER
    assert dep.critical is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"serviceName": ""},
        {"serviceName": "   "},
        {"systemOwner": ""},
        {"rtoMinutes": 0},
        {"rtoMinutes": -1},
        {"rpoMinutes": 0},
        {"unknownField": 1},
        {"dependencies": [{"name": "x", "type": "quantum"}]},
        {"steps": [{"stepNumber": 0, "action": "a", "owner": "o", "estimatedMinutes": 1}]},
        {"steps": [{"stepNumber": 1, "action": "", "owner": "o", "estimatedMinutes": 1}]},
        {"steps": [{"stepNumber": 1, "action": "a", "owner": "o", "estimatedMinutes": 0}]},
    ],
)
def test_runbook_rejects_invalid(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_runbook(**overrides)


def _step(number: int, deps: list[int] | None = None) -> dict[str, object]:
    return {
        "stepNumber": number,
        "action": "a",
        "owner": "o",
        "estimatedMinutes": 1,
        "dependsOn": deps or [],
    }


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([_step(1), _step(1)], "unique"),
        ([_step(1, [1])], "itself"),
        ([_step(1, [9])], "unknown step 9"),
    ],
)
def test_runbook_step_graph_validation(steps: list[dict[str, object]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make_runbook(steps=steps)


def test_step_model_direct() -> None:
    step = Step(step_number=1, action="Do it", owner="Dana", estimated_minutes=2.5)
    assert step.validation_command is None


def test_inventory_defaults_and_mock_fields() -> None:
    inv = SystemInventory.model_validate(
        {
            "services": [
                {"name": "pg", "endpoint": "https://pg.example.com", "type": "database"},
                {
                    "name": "kafka",
                    "endpoint": "https://k.example.com",
                    "type": "messaging",
                    "region": "eu-west-1",
                    "mockStatus": "DOWN",
                    "mockLatencyMs": 120,
                },
            ]
        }
    )
    pg, kafka = inv.services
    assert pg.expected_status == "UP"
    assert pg.mock_status is HealthStatus.UP
    assert pg.mock_latency_ms is None
    assert kafka.mock_status is HealthStatus.DOWN
    assert kafka.region == "eu-west-1"


@pytest.mark.parametrize(
    "service",
    [
        {"name": "x", "endpoint": "not a url", "type": "database"},
        {"name": "x", "endpoint": "https://x.io", "type": "other"},
        {"name": "x", "endpoint": "https://x.io", "type": "database", "expectedStatus": "DOWN"},
        {"name": "x", "endpoint": "https://x.io", "type": "database", "mockStatus": "MAYBE"},
        {"name": "x", "endpoint": "https://x.io", "type": "database", "mockLatencyMs": -1},
        {"name": "", "endpoint": "https://x.io", "type": "database"},
    ],
)
def test_inventory_rejects_invalid(service: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SystemInventory.model_validate({"services": [service]})


def test_empty_inventory_is_valid() -> None:
    assert SystemInventory().services == []


def test_service_status_shape() -> None:
    status = ServiceStatus(
        name="pg", endpoint="https://pg", status=HealthStatus.UNREACHABLE, latency_ms=3000
    )
    assert status.to_json_dict() == {
        "name": "pg",
        "endpoint": "https://pg",
        "status": "UNREACHABLE",
        "latencyMs": 3000.0,
        "error": None,
    }
    with pytest.raises(ValidationError):
        ServiceStatus(name="pg", endpoint="e", status=HealthStatus.UP, latency_ms=-1)


def test_inventory_service_direct() -> None:
    svc = InventoryService.model_validate(
        {"name": "v", "endpoint": "http://vault:8200", "type": "secrets"}
    )
    assert str(svc.endpoint).startswith("http://vault")
