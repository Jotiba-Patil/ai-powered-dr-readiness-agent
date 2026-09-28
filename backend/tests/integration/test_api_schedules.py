"""Schedule API: disabled state, CRUD and validation, run now, stored analysis and email."""

from __future__ import annotations

from pathlib import Path

import pytest
from schedule_api_support import OWNER_EMAIL, SCHEDULES, create, run_now, schedule_client

from conftest import ClientFactory


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", SCHEDULES),
        ("POST", f"{SCHEDULES}/abc/run-now"),
        ("GET", "/api/v1/scheduler"),
        ("POST", "/api/v1/schedule-runs/abc/cancel"),
    ],
)
def test_everything_is_403_while_disabled(
    make_client: ClientFactory, method: str, path: str
) -> None:
    response = make_client().request(method, path)
    assert response.status_code == 403
    assert response.json()["code"] == "SCHEDULER_DISABLED"


def test_create_read_update_delete(tmp_path: Path) -> None:
    with schedule_client(tmp_path, scheduler_default_timezone="Europe/Berlin") as (client, _):
        created = create(client)
        assert created["timezone"] == "Europe/Berlin"  # the server default when left out
        assert created["description"] == "Hourly at :15 Europe/Berlin"
        assert created["enabled"] is True
        assert created["nextRunAt"] is not None
        assert created["lastRun"] is None
        schedule_id = created["id"]
        listed = client.get(SCHEDULES).json()
        assert [s["id"] for s in listed] == [schedule_id]
        body = {
            "name": "Estimate daily",
            "runbookPath": "runbooks/estimate-service.md",
            "cadence": {"kind": "daily", "time": "06:00"},
            "timezone": "UTC",
            "recipients": ["ops@example.com"],
        }
        updated = client.put(f"{SCHEDULES}/{schedule_id}", json=body).json()
        assert (updated["name"], updated["description"]) == ("Estimate daily", "Daily 06:00 UTC")
        assert updated["recipients"] == ["ops@example.com"]
        assert updated["inventoryPath"] is None
        assert client.delete(f"{SCHEDULES}/{schedule_id}").status_code == 204
        assert client.get(f"{SCHEDULES}/{schedule_id}").status_code == 404


@pytest.mark.parametrize(
    ("fields", "status", "code"),
    [
        ({"runbookPath": "../pyproject.toml"}, 403, "PATH_NOT_ALLOWED"),
        ({"runbookPath": "runbooks/nope.md"}, 404, "NOT_FOUND"),
        ({"timezone": "Mars/Olympus"}, 422, "VALIDATION_ERROR"),
        ({"cadence": {"kind": "cron", "expression": "* * * * *"}}, 422, "VALIDATION_ERROR"),
        ({"recipients": ["not an address"]}, 422, "VALIDATION_ERROR"),
        ({"createdBy": ""}, 422, "VALIDATION_ERROR"),
        ({"execute": True}, 422, "VALIDATION_ERROR"),
    ],
)
def test_bad_schedules_are_refused(
    tmp_path: Path, fields: dict[str, object], status: int, code: str
) -> None:
    body = {
        "name": "x",
        "runbookPath": "runbooks/estimate-service.md",
        "cadence": {"kind": "hourly", "minute": 0},
        "createdBy": "Alice",
        **fields,
    }
    with schedule_client(tmp_path) as (client, _):
        response = client.post(SCHEDULES, json=body)
        assert (response.status_code, response.json()["code"]) == (status, code)
        assert client.get(SCHEDULES).json() == []


def test_schedule_limit(tmp_path: Path) -> None:
    with schedule_client(tmp_path, scheduler_max_schedules=1) as (client, _):
        create(client)
        second = client.post(
            SCHEDULES,
            json={
                "name": "y",
                "runbookPath": "runbooks/estimate-service.md",
                "cadence": {"kind": "hourly", "minute": 0},
                "createdBy": "Alice",
            },
        )
        assert (second.status_code, second.json()["code"]) == (409, "CONFLICT")


def test_run_now_stores_the_analysis_and_emails_the_owner(tmp_path: Path) -> None:
    with schedule_client(tmp_path) as (client, notifier):
        schedule_id = create(client)["id"]
        run = run_now(client, str(schedule_id))
        assert run["state"] == "succeeded", run
        assert run["trigger"] == "manual"
        assert run["analysisId"] == run["jobId"]
        assert (run["emailState"], run["emailTo"]) == ("sent", [OWNER_EMAIL])
        stored = client.get(f"/api/v1/analyses/{run['analysisId']}").json()
        assert stored["summary"]["source"] == "scheduled"
        assert stored["report"]["riskScore"] == run["riskScore"]
        [message] = notifier.sent
        assert message["To"] == OWNER_EMAIL
        text = message.get_body(("plain",)).get_content()  # type: ignore[union-attr]
        assert f"#/schedules/{schedule_id}/runs/{run['id']}" in text
        page = client.get(f"{SCHEDULES}/{schedule_id}/runs").json()
        assert [r["id"] for r in page["items"]] == [run["id"]]
        assert page["nextBefore"] is None
        listed = client.get(SCHEDULES).json()
        assert listed[0]["lastRun"]["id"] == run["id"]
        one = client.get(f"{SCHEDULES}/{schedule_id}/runs", params={"limit": 1}).json()
        assert one["nextBefore"] is not None


def test_unknown_ids_are_404(tmp_path: Path) -> None:
    with schedule_client(tmp_path) as (client, _):
        assert client.get(f"{SCHEDULES}/nope/runs").status_code == 404
        assert client.post(f"{SCHEDULES}/nope/run-now").status_code == 404
        assert client.get("/api/v1/schedule-runs/nope").status_code == 404
        assert client.get(f"{SCHEDULES}/bad id").status_code == 422
