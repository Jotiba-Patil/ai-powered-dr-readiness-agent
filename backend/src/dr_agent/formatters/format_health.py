"""Health-check results (the CLI `validate` command) -> Rich table or JSON."""

from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.table import Table

from dr_agent.models.inventory import HealthStatus, ServiceStatus

_STATUS_STYLES = {
    HealthStatus.UP: "green",
    HealthStatus.DOWN: "red",
    HealthStatus.UNREACHABLE: "red",
}


def format_health_json(statuses: list[ServiceStatus]) -> str:
    return json.dumps([status.to_json_dict() for status in statuses], indent=2)


def render_health_terminal(statuses: list[ServiceStatus], *, console: Console) -> None:
    table = Table(title="Inventory health", box=box.ASCII)
    table.add_column("Service")
    table.add_column("Status")
    table.add_column("Latency (ms)", justify="right")
    table.add_column("Error")
    for status in statuses:
        style = _STATUS_STYLES[status.status]
        table.add_row(
            status.name,
            f"[{style}]{status.status.value}[/{style}]",
            f"{status.latency_ms:.0f}",
            status.error or "",
        )
    console.print(table)
    up = sum(1 for status in statuses if status.status is HealthStatus.UP)
    console.print(f"{up}/{len(statuses)} services UP")
