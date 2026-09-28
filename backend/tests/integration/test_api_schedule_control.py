"""Schedule API control: pause, pause all, cancel, preview, execution from a run, real SMTP."""

from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Message
from exec_api_support import OPERATOR
from schedule_api_support import OWNER_EMAIL, SCHEDULES, create, run_now, schedule_client

from conftest import REPO, BlockingProvider
from dr_agent.scheduling.models import ScheduleRun
from dr_agent.scheduling.sqlite_store import SqliteScheduleStore

SOON = (datetime.now(UTC) + timedelta(days=1)).isoformat()


def test_pause_until_and_resume(tmp_path: Path) -> None:
    with schedule_client(tmp_path) as (client, _):
        schedule_id = create(client)["id"]
        too_far = (datetime.now(UTC) + timedelta(days=91)).isoformat()
        refused = client.post(
            f"{SCHEDULES}/{schedule_id}/pause", json={"by": "Bob", "until": too_far}
        )
        assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
        paused = client.post(f"{SCHEDULES}/{schedule_id}/pause", json={"by": "Bob", "until": SOON})
        body = paused.json()
        assert (body["enabled"], body["pausedBy"], body["nextRunAt"]) == (False, "Bob", None)
        assert body["pauseUntil"] is not None
        resumed = client.post(f"{SCHEDULES}/{schedule_id}/resume", json={"by": "Bob"}).json()
        assert (resumed["enabled"], resumed["pauseUntil"]) == (True, None)
        assert resumed["nextRunAt"] is not None
        assert client.post(f"{SCHEDULES}/{schedule_id}/resume", json={}).status_code == 422


def test_pause_all_and_scheduler_view(tmp_path: Path) -> None:
    secret = {"smtp_password": "s3cret"}  # a fake password that must never reach a response
    with schedule_client(tmp_path, **secret) as (client, _):
        view = client.get("/api/v1/scheduler").json()
        assert view["paused"] is False
        assert (view["emailTransport"], view["defaultRecipient"]) == ("log", True)
        assert view["allowedDomains"] == ["example.com"]
        assert "s3cret" not in str(view)
        paused = client.post("/api/v1/scheduler/pause", json={"by": "Bob", "until": SOON}).json()
        assert (paused["paused"], paused["pausedBy"]) == (True, "Bob")
        resumed = client.post("/api/v1/scheduler/resume", json={"by": "Bob"}).json()
        assert resumed["paused"] is False


def test_cancel_a_running_run(tmp_path: Path) -> None:
    with schedule_client(tmp_path, llm=BlockingProvider(), llm_provider="ollama") as (client, log):
        schedule_id = create(client)["id"]
        started = client.post(f"{SCHEDULES}/{schedule_id}/run-now").json()
        again = client.post(f"{SCHEDULES}/{schedule_id}/run-now")
        assert (again.status_code, again.json()["code"]) == (409, "CONFLICT")
        cancelled = client.post(f"/api/v1/schedule-runs/{started['id']}/cancel").json()
        assert cancelled["state"] == "cancelled"
        assert not log.sent
        repeat = client.post(f"/api/v1/schedule-runs/{started['id']}/cancel")
        assert repeat.status_code == 409


def test_recipient_preview(tmp_path: Path) -> None:
    with schedule_client(tmp_path) as (client, _):
        url = "/api/v1/scheduler/recipient-preview"
        owner = client.get(url, params={"runbookPath": "runbooks/estimate-service.md"}).json()
        assert owner == {
            "addresses": [OWNER_EMAIL],
            "source": "directory",
            "ownerFound": True,
            "dropped": 0,
        }
        override = client.get(
            url,
            params={
                "runbookPath": "runbooks/estimate-service.md",
                "recipients": ["a@example.com", "b@evil.org"],
            },
        ).json()
        assert (override["addresses"], override["source"], override["dropped"]) == (
            ["a@example.com"],
            "override",
            1,
        )
        traversal = client.get(url, params={"runbookPath": "../pyproject.toml"})
        assert traversal.status_code == 403


def test_a_scheduled_run_is_executed_with_the_existing_endpoint(tmp_path: Path) -> None:
    extra = {
        "execution_enabled": True,
        "execution_policy_file": str(REPO / "execution-policy.json"),
        "mcp_servers_file": str(tmp_path / "no-servers.json"),
    }
    (tmp_path / "no-servers.json").write_text("{}", encoding="utf-8")
    with schedule_client(tmp_path, **extra) as (client, _):
        schedule_id = create(client, runbookPath="runbooks/estimate-service-executable.md")["id"]
        run = run_now(client, str(schedule_id))
        created = client.post(
            "/api/v1/executions",
            json={"analysisJobId": run["analysisId"], "mode": "dry_run", "startedBy": OPERATOR},
        )
        assert created.status_code == 201, created.text
        assert created.json()["analysis"]["jobId"] == run["analysisId"]
        runs = client.get(f"/api/v1/analyses/{run['analysisId']}/executions").json()
        assert len(runs) == 1


class Inbox(Message):
    def __init__(self) -> None:
        super().__init__()
        self.received: list[str] = []

    def handle_message(self, message: object) -> None:
        self.received.append(str(message))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_email_is_delivered_over_smtp(tmp_path: Path) -> None:
    inbox = Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=free_port())
    controller.start()
    try:
        smtp = {"notify_transport": "smtp", "smtp_host": "127.0.0.1", "smtp_port": controller.port}
        with schedule_client(tmp_path, capture=False, **smtp) as (client, _):
            run = run_now(client, str(create(client)["id"]))
    finally:
        controller.stop()
    assert (run["emailState"], run["emailTo"]) == ("sent", [OWNER_EMAIL])
    [raw] = inbox.received
    assert f"To: {OWNER_EMAIL}" in raw
    assert "Subject: [DR readiness] Estimate-Service:" in raw


def test_shutdown_marks_a_running_run_interrupted(tmp_path: Path) -> None:
    blocking = {"llm": BlockingProvider(), "llm_provider": "ollama"}
    with schedule_client(tmp_path, **blocking) as (client, log):  # type: ignore[arg-type]
        schedule_id = create(client)["id"]
        run_id = client.post(f"{SCHEDULES}/{schedule_id}/run-now").json()["id"]
    run = asyncio.run(_stored_run(tmp_path, run_id))
    assert (run.state.value, run.error_code) == ("failed", "INTERRUPTED")
    assert not log.sent


async def _stored_run(tmp_path: Path, run_id: str) -> ScheduleRun:
    store = await SqliteScheduleStore.open(tmp_path / "dr-agent.db")
    return await store.get_run(run_id)
