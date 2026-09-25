"""Executions from stored analyses: after a restart, linked, and protecting their source."""

from __future__ import annotations

from pathlib import Path

from exec_api_support import BASE, OPERATOR, analyze, execution_client

HISTORY = "/api/v1/analyses"


def test_a_stored_analysis_can_be_executed_after_a_restart(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _env):
        job_id = analyze(client)
    with execution_client(tmp_path) as (client, _env):
        created = client.post(
            BASE, json={"analysisJobId": job_id, "mode": "dry_run", "startedBy": OPERATOR}
        )
        assert created.status_code == 201, created.text
        execution = created.json()
        assert execution["analysis"]["jobId"] == job_id
        linked = client.get(f"{HISTORY}/{job_id}/executions").json()
        assert [e["id"] for e in linked] == [execution["id"]]
        assert client.get(f"{HISTORY}/{job_id}").json()["summary"]["executionCount"] == 1
        refused = client.delete(f"{HISTORY}/{job_id}")
        assert (refused.status_code, refused.json()["code"]) == (409, "CONFLICT")
        assert refused.json()["details"] == {"executions": 1}


def test_executions_stay_listed_when_execution_is_switched_off(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _env):
        job_id = analyze(client)
        created = client.post(
            BASE, json={"analysisJobId": job_id, "mode": "dry_run", "startedBy": OPERATOR}
        )
        assert created.status_code == 201
    with execution_client(tmp_path, execution_enabled=False) as (client, _env):
        linked = client.get(f"{HISTORY}/{job_id}/executions").json()
        assert [e["id"] for e in linked] == [created.json()["id"]]


def test_unknown_or_unfinished_analyses_cannot_be_executed(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _env):
        missing = client.post(
            BASE, json={"analysisJobId": "nope", "mode": "dry_run", "startedBy": OPERATOR}
        )
        assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


def test_history_shows_one_execution_read_only(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _env):
        job_id = analyze(client)
        other = analyze(client)
        created = client.post(
            BASE, json={"analysisJobId": job_id, "mode": "dry_run", "startedBy": OPERATOR}
        ).json()
    with execution_client(tmp_path, execution_enabled=False) as (client, _env):
        stored = client.get(f"{HISTORY}/{job_id}/executions/{created['id']}").json()
        assert stored["execution"]["id"] == created["id"]
        assert stored["execution"]["steps"]
        verification = stored["audit"]["verification"]
        assert (verification["valid"], verification["events"]) == (
            True,
            len(stored["audit"]["events"]),
        )
        wrong = client.get(f"{HISTORY}/{other}/executions/{created['id']}")
        assert (wrong.status_code, wrong.json()["code"]) == (404, "NOT_FOUND")
        missing = client.get(f"{HISTORY}/{job_id}/executions/nope")
        assert missing.status_code == 404
