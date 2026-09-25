"""Execution API: switches, tools, a full live run, errors and the audit chain."""

from pathlib import Path

from exec_api_support import (
    BASE,
    OPERATOR,
    SAMPLE,
    act,
    analyze,
    approve_all,
    call_hash,
    create,
    execution_client,
    step,
)

from conftest import BlockingProvider, ClientFactory


def test_disabled_by_default(make_client: ClientFactory) -> None:
    client = make_client()
    settings = client.get("/api/v1/execution/settings").json()
    assert settings["enabled"] is False
    assert settings["identityVerified"] is False
    assert settings["approvalsByRisk"] == {"read": 1, "write": 1, "destructive": 2}
    for method, path in (("get", "/api/v1/tools"), ("get", BASE), ("post", BASE)):
        response = client.request(method.upper(), path, json={})
        assert response.status_code == 403
        assert response.json()["code"] == "EXECUTION_DISABLED"


def test_tools_carry_their_effective_risk(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _):
        tools = {t["name"]: t for t in client.get("/api/v1/tools").json()}
        assert len(tools) == 9
        assert tools["db_promote_replica"]["risk"] == "destructive"
        assert tools["smoke_run"]["risk"] == "read"
        assert "properties" in tools["cache_ping"]["inputSchema"]
        assert client.get("/api/v1/execution/settings").json()["enabled"] is True


def test_full_live_run_through_the_api(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, env):
        execution = create(client)
        assert execution["state"] == "CREATED"
        assert [s["state"] for s in execution["steps"]] == ["AWAITING_APPROVAL"] * 5
        execution = approve_all(client, execution)
        assert {s["state"] for s in execution["steps"]} == {"APPROVED"}

        execution = act(client, execution["id"], "start")()
        assert step(execution, 1)["state"] == "VERIFYING"  # no verify tool: a person confirms
        verify = {"actor": "Ann", "succeeded": True, "reason": "primary is down"}
        execution = act(client, execution["id"], "steps/1/verify", verify)()
        assert execution["state"] == "COMPLETED"
        assert env.state.dns["estimate-service"] == "standby"

        listed = client.get(BASE).json()
        assert listed[0]["id"] == execution["id"]
        assert listed[0]["steps"] == 5
        audit = client.get(f"{BASE}/{execution['id']}/audit", params={"verify": True}).json()
        assert audit["verification"]["valid"] is True
        assert audit["verification"]["head"] == execution["auditHead"]
        assert client.get(f"{BASE}/{execution['id']}/audit").json()["verification"] is None


def test_dry_run_never_calls_the_server(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, env):
        execution = approve_all(client, create(client, mode="dry_run"))
        act(client, execution["id"], "start")()
        verify = {"actor": "Ann", "succeeded": True}
        execution = act(client, execution["id"], "steps/1/verify", verify)()
        assert execution["state"] == "COMPLETED"
        assert sum(env.call_counts.values()) == 0
        assert step(execution, 5)["call"]["result"]["simulated"] is True


def test_live_mode_needs_the_second_switch(tmp_path: Path) -> None:
    with execution_client(tmp_path, execution_allow_live=False) as (client, _):
        body = {"analysisJobId": analyze(client), "mode": "live", "startedBy": OPERATOR}
        blocked = client.post(BASE, json=body)
        assert blocked.status_code == 403
        assert blocked.json()["code"] == "EXECUTION_DISABLED"


def test_execution_needs_a_finished_analysis(tmp_path: Path) -> None:
    with execution_client(tmp_path, llm=BlockingProvider()) as (client, _):
        unknown = client.post(BASE, json={"analysisJobId": "nope", "startedBy": OPERATOR})
        assert (unknown.status_code, unknown.json()["code"]) == (404, "NOT_FOUND")
        running = client.post(
            "/api/v1/dr/analyze", json={"runbookMarkdown": SAMPLE, "runbookName": "s.md"}
        ).json()["jobId"]
        early = client.post(BASE, json={"analysisJobId": running, "startedBy": OPERATOR})
        assert (early.status_code, early.json()["code"]) == (409, "CONFLICT")
        no_text = client.post(BASE, json={"runbookMarkdown": SAMPLE, "startedBy": OPERATOR})
        assert no_text.status_code == 422  # raw runbook text is no longer accepted


def test_execution_records_its_analysis_and_follows_the_report_plan(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _):
        job_id = analyze(client)
        report = client.get(f"/api/v1/dr/jobs/{job_id}").json()["report"]
        execution = client.post(
            BASE, json={"analysisJobId": job_id, "mode": "dry_run", "startedBy": OPERATOR}
        ).json()
        assert execution["analysis"]["jobId"] == job_id
        assert execution["analysis"]["riskScore"] == report["riskScore"]
        phases = {s["stepNumber"]: s["phase"] for s in execution["steps"]}
        planned = {n: p["phase"] for p in report["executionPlan"] for n in p["steps"]}
        assert phases == planned
        assert client.get(BASE).json()[0]["analysisJobId"] == job_id
        audit = client.get(f"{BASE}/{execution['id']}/audit").json()["events"]
        assert audit[0]["payload"]["analysis"]["jobId"] == job_id


def test_approval_errors(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _):
        execution = create(client)
        url = f"{BASE}/{execution['id']}/steps/3/approve"
        stale = client.post(url, json={"approver": "Ann", "callHash": "0" * 64})
        assert (stale.status_code, stale.json()["code"]) == (409, "STALE_CALL")
        own = client.post(url, json={"approver": OPERATOR, "callHash": call_hash(execution, 3)})
        assert (own.status_code, own.json()["code"]) == (422, "POLICY_VIOLATION")
        bad = client.post(url, json={"approver": "Ann", "callHash": "nothex"})
        assert (bad.status_code, bad.json()["code"]) == (422, "VALIDATION_ERROR")
        missing = client.get(f"{BASE}/nope")
        assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
        wrong_state = client.post(f"{BASE}/{execution['id']}/resume", json={"actor": OPERATOR})
        assert (wrong_state.status_code, wrong_state.json()["code"]) == (409, "INVALID_TRANSITION")
        no_step = client.post(
            f"{BASE}/{execution['id']}/steps/9/skip", json={"actor": "A", "reason": "r"}
        )
        assert no_step.status_code == 404
