"""Helpers for the schedule API tests: an app with the scheduler on and emails captured."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from conftest import MOCK, mock_checker
from dr_agent.api.app import create_app
from dr_agent.api.deps import AppState
from dr_agent.config import Settings
from dr_agent.llm.base import LLMProvider
from dr_agent.notify.senders import LogNotifier, Notifier

Json = dict[str, object]
SCHEDULES = "/api/v1/schedules"
OWNER_EMAIL = "alice.chen@example.com"  # **Owner:** Alice Chen in estimate-service.md


@contextmanager
def schedule_client(
    tmp_path: Path,
    *,
    llm: LLMProvider | None = None,
    notifier: Notifier | None = None,
    capture: bool = True,
    **overrides: object,
) -> Iterator[tuple[TestClient, LogNotifier]]:
    """TestClient with SCHEDULER_ENABLED=true and the mock data folder.

    Emails go to the returned `LogNotifier`; `capture=False` uses the notifier the
    settings describe (e.g. `NOTIFY_TRANSPORT=smtp`).
    """
    log = LogNotifier()
    values: dict[str, object] = {
        "llm_provider": "none",
        "api_allowed_dir": str(MOCK),
        "db_path": str(tmp_path / "dr-agent.db"),
        "scheduler_enabled": True,
        "scheduler_tick_seconds": 3600,  # the tests drive runs with run-now
        "notify_contacts_file": str(MOCK / "contacts.json"),
        "notify_default_email": "dr-team@example.com",
        "ui_base_url": "http://localhost:8080",
        **overrides,
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
    chosen = (notifier or log) if capture else None
    app = create_app(settings, llm=llm, checker=mock_checker(), notifier=chosen)
    with TestClient(app) as client:
        yield client, log


def state_of(client: TestClient) -> AppState:
    return cast(AppState, client.app.state.dr)  # type: ignore[attr-defined]  # Starlette app


def settle(client: TestClient) -> None:
    """Waits until every scheduled run in progress has finished."""
    schedules = state_of(client).schedules
    assert schedules is not None
    client.portal.call(schedules.scheduler.wait_idle)  # type: ignore[union-attr]  # entered client


def create(client: TestClient, **fields: object) -> Json:
    body: Json = {
        "name": "Estimate hourly",
        "runbookPath": "runbooks/estimate-service.md",
        "inventoryPath": "inventories/healthy.json",
        "cadence": {"kind": "hourly", "minute": 15},
        "createdBy": "Alice",
        **fields,
    }
    response = client.post(SCHEDULES, json=body)
    assert response.status_code == 201, response.text
    return cast(Json, response.json())


def run_now(client: TestClient, schedule_id: str) -> Json:
    """Starts a run, waits for it and returns the finished run."""
    started = client.post(f"{SCHEDULES}/{schedule_id}/run-now")
    assert started.status_code == 202, started.text
    settle(client)
    return cast(Json, client.get(f"/api/v1/schedule-runs/{started.json()['id']}").json())
