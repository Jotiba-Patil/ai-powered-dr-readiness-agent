import random

import pytest

from dr_agent.health.mock import MockHealthChecker
from dr_agent.models.inventory import HealthStatus, InventoryService


async def _noop_sleep(_seconds: float) -> None:
    return None


def _service(
    name: str, status: HealthStatus = HealthStatus.UP, latency_ms: float | None = None
) -> InventoryService:
    return InventoryService.model_validate(
        {
            "name": name,
            "endpoint": f"https://health.internal/{name}",
            "type": "database",
            "mockStatus": status.value,
            **({"mockLatencyMs": latency_ms} if latency_ms is not None else {}),
        }
    )


async def test_up_service_has_no_error_and_matching_status() -> None:
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)
    results = await checker.check_all([_service("svc-a")])
    assert results[0].status is HealthStatus.UP
    assert results[0].error is None


async def test_down_and_unreachable_services_carry_an_error() -> None:
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)
    results = await checker.check_all(
        [
            _service("down-svc", HealthStatus.DOWN),
            _service("unreachable-svc", HealthStatus.UNREACHABLE),
        ]
    )
    assert results[0].status is HealthStatus.DOWN
    assert results[0].error is not None
    assert results[1].status is HealthStatus.UNREACHABLE
    assert results[1].error is not None


async def test_results_preserve_input_order() -> None:
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)
    services = [_service(f"svc-{i}") for i in range(5)]
    results = await checker.check_all(services)
    assert [r.name for r in results] == [s.name for s in services]


async def test_explicit_mock_latency_is_used_verbatim() -> None:
    checker = MockHealthChecker(random.Random(1), sleeper=_noop_sleep)
    results = await checker.check_all([_service("svc-a", latency_ms=123.0)])
    assert results[0].latency_ms == 123.0


async def test_default_latency_falls_within_configured_range() -> None:
    checker = MockHealthChecker(
        random.Random(1), sleeper=_noop_sleep, latency_range_ms=(50.0, 200.0)
    )
    results = await checker.check_all([_service("svc-a") for _ in range(20)])
    assert all(50.0 <= r.latency_ms <= 200.0 for r in results)


async def test_sleeper_is_awaited_once_per_service() -> None:
    calls: list[float] = []

    async def spy_sleep(seconds: float) -> None:
        calls.append(seconds)

    checker = MockHealthChecker(random.Random(1), sleeper=spy_sleep)
    await checker.check_all([_service("a", latency_ms=10.0), _service("b", latency_ms=20.0)])
    assert calls == [0.01, 0.02]


@pytest.mark.parametrize("seed", [1, 7, 42])
async def test_chaos_outcomes_are_deterministic_for_a_given_seed(seed: int) -> None:
    services = [_service(f"svc-{i}") for i in range(15)]
    checker_a = MockHealthChecker(random.Random(seed), chaos=True, sleeper=_noop_sleep)
    checker_b = MockHealthChecker(random.Random(seed), chaos=True, sleeper=_noop_sleep)

    results_a = await checker_a.check_all(services)
    results_b = await checker_b.check_all(services)

    assert [r.status for r in results_a] == [r.status for r in results_b]


async def test_chaos_can_turn_an_up_service_unreachable() -> None:
    """chaos_failure_rate=1.0 makes every check fail regardless of mock_status."""
    checker = MockHealthChecker(
        random.Random(1), chaos=True, chaos_failure_rate=1.0, sleeper=_noop_sleep
    )
    results = await checker.check_all([_service("svc-a", HealthStatus.UP)])
    assert results[0].status is HealthStatus.UNREACHABLE
    assert results[0].error == "simulated chaos failure"


async def test_chaos_disabled_never_overrides_status() -> None:
    checker = MockHealthChecker(random.Random(1), chaos=False, sleeper=_noop_sleep)
    results = await checker.check_all([_service(f"svc-{i}") for i in range(30)])
    assert all(r.status is HealthStatus.UP for r in results)
