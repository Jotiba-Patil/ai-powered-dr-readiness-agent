import httpx

from dr_agent.health.live import LiveHealthChecker
from dr_agent.models.inventory import HealthStatus, InventoryService


def _service(name: str, endpoint: str = "https://svc.internal/health") -> InventoryService:
    return InventoryService.model_validate({"name": name, "endpoint": endpoint, "type": "database"})


def _checker(handler: httpx.MockTransport, timeout_seconds: float = 1.0) -> LiveHealthChecker:
    client = httpx.AsyncClient(transport=handler)
    return LiveHealthChecker(client, timeout_seconds)


async def test_2xx_response_is_up() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    results = await _checker(transport).check_all([_service("svc-a")])
    assert results[0].status is HealthStatus.UP
    assert results[0].error is None


async def test_error_response_is_down() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    results = await _checker(transport).check_all([_service("svc-a")])
    assert results[0].status is HealthStatus.DOWN
    assert results[0].error == "HTTP 503"


async def test_timeout_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    transport = httpx.MockTransport(handler)
    results = await _checker(transport).check_all([_service("svc-a")])
    assert results[0].status is HealthStatus.UNREACHABLE
    assert results[0].error == "timed out"


async def test_connection_error_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(handler)
    results = await _checker(transport).check_all([_service("svc-a")])
    assert results[0].status is HealthStatus.UNREACHABLE
    assert results[0].error == "refused"


async def test_unexpected_exception_is_caught_as_unreachable() -> None:
    """gather(..., return_exceptions=True) is a safety net for non-HTTPError failures."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("boom")

    transport = httpx.MockTransport(handler)
    results = await _checker(transport).check_all([_service("svc-a")])
    assert results[0].status is HealthStatus.UNREACHABLE
    assert "boom" in (results[0].error or "")


async def test_checks_multiple_services_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if str(request.url).endswith("/a") else 500)

    transport = httpx.MockTransport(handler)
    services = [
        _service("svc-a", "https://svc.internal/a"),
        _service("svc-b", "https://svc.internal/b"),
    ]
    results = await _checker(transport).check_all(services)
    assert [r.name for r in results] == ["svc-a", "svc-b"]
    assert results[0].status is HealthStatus.UP
    assert results[1].status is HealthStatus.DOWN
