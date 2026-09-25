import io
import json

from rich.console import Console

from dr_agent.formatters.format_health import format_health_json, render_health_terminal
from dr_agent.models.inventory import HealthStatus, ServiceStatus

STATUSES = [
    ServiceStatus(name="db", endpoint="http://db/", status=HealthStatus.UP, latency_ms=12.4),
    ServiceStatus(
        name="cache",
        endpoint="http://cache/",
        status=HealthStatus.DOWN,
        latency_ms=80,
        error="mock status is DOWN",
    ),
]


def test_json_uses_camel_case_list() -> None:
    data = json.loads(format_health_json(STATUSES))
    assert [row["name"] for row in data] == ["db", "cache"]
    assert data[0]["latencyMs"] == 12.4


def test_terminal_table_lists_services_and_up_count() -> None:
    buffer = io.StringIO()
    render_health_terminal(STATUSES, console=Console(file=buffer, width=100))
    text = buffer.getvalue()
    assert "db" in text
    assert "mock status is DOWN" in text
    assert "1/2 services UP" in text
