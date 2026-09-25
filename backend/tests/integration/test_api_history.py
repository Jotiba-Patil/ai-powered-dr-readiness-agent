"""Analysis history API (design analysis-history section 6): stored, listed, kept over restarts."""

from __future__ import annotations

import sqlite3
from typing import cast

import pytest
from fastapi.testclient import TestClient

from conftest import MOCK, ClientFactory
from dr_agent.history.models import AnalysisRecord
from dr_agent.history.sqlite_store import SqliteAnalysisStore
from dr_agent.llm.prompts.analysis import PROMPT_VERSION

BASE = "/api/v1/analyses"


def _analyze(client: TestClient, runbook: str = "runbooks/estimate-service.md") -> str:
    params = {"runbook": runbook, "inventory": "inventories/healthy.json"}
    submitted = client.get("/api/v1/dr/analyze", params=params)
    assert submitted.status_code == 202, submitted.text
    job_id = cast(str, submitted.json()["jobId"])
    done = client.get(f"/api/v1/dr/jobs/{job_id}", params={"wait": True}).json()
    assert done["status"] == "succeeded", done
    assert done["historySaved"] is True
    return job_id


def test_finished_analyses_are_stored_and_listed(make_client: ClientFactory) -> None:
    client = make_client()
    first = _analyze(client)
    second = _analyze(client, "runbooks/payment-gateway.md")
    page = client.get(BASE).json()
    assert [item["id"] for item in page["items"]] == [second, first]
    assert page["nextBefore"] is None
    item = page["items"][1]
    assert (item["serviceName"], item["source"], item["inventoryLabel"]) == (
        "Estimate Service",
        "api",
        "inventories/healthy.json",
    )
    assert item["executionCount"] == 0
    only = client.get(BASE, params={"service": "Estimate Service"}).json()["items"]
    assert [i["id"] for i in only] == [first]
    one = client.get(BASE, params={"limit": 1}).json()
    assert [i["id"] for i in one["items"]] == [second]
    rest = client.get(BASE, params={"limit": 1, "before": one["nextBefore"]}).json()
    assert [i["id"] for i in rest["items"]] == [first]


def test_detail_runbook_report_and_executions(make_client: ClientFactory) -> None:
    client = make_client()
    job_id = _analyze(client)
    detail = client.get(f"{BASE}/{job_id}").json()
    assert detail["summary"]["id"] == job_id
    assert detail["report"]["serviceSummary"]["name"] == "Estimate Service"
    assert detail["provenance"] == {
        "llmProvider": "none",
        "llmModel": None,
        "promptVersion": PROMPT_VERSION,
        "agentVersion": detail["report"]["meta"]["agentVersion"],
    }
    assert detail["stale"] is False
    runbook = client.get(f"{BASE}/{job_id}/runbook")
    assert runbook.headers["content-type"].startswith("text/plain")
    assert runbook.headers["content-disposition"] == f'attachment; filename="runbook-{job_id}.md"'
    expected = (MOCK / "runbooks" / "estimate-service.md").read_text("utf-8")
    assert runbook.text.strip() == expected.strip()
    html = client.get(f"{BASE}/{job_id}/report.html")
    assert html.status_code == 200
    assert "default-src 'none'" in html.headers["content-security-policy"]
    assert client.get(f"{BASE}/{job_id}/executions").json() == []


def test_delete_and_unknown_ids(make_client: ClientFactory) -> None:
    client = make_client()
    job_id = _analyze(client)
    assert client.delete(f"{BASE}/{job_id}").status_code == 204
    for path in ("", "/runbook", "/report.html", "/executions"):
        missing = client.get(f"{BASE}/{job_id}{path}")
        assert missing.status_code == 404, path
        assert missing.json()["code"] == "NOT_FOUND"
    assert client.delete(f"{BASE}/{job_id}").status_code == 404


def test_reports_survive_a_restart(make_client: ClientFactory) -> None:
    job_id = _analyze(make_client())
    restarted = make_client()
    job = restarted.get(f"/api/v1/dr/jobs/{job_id}", params={"wait": True}).json()
    assert (job["status"], job["historySaved"]) == ("succeeded", True)
    assert job["report"]["serviceSummary"]["name"] == "Estimate Service"
    assert restarted.get(f"/api/v1/dr/jobs/{job_id}/report.html").status_code == 200
    assert restarted.get("/api/v1/dr/jobs/unknown").status_code == 404


def test_history_can_be_switched_off(make_client: ClientFactory) -> None:
    client = make_client(history_enabled=False)
    submitted = client.get("/api/v1/dr/analyze", params={"runbook": "runbooks/estimate-service.md"})
    job = client.get(f"/api/v1/dr/jobs/{submitted.json()['jobId']}", params={"wait": True}).json()
    assert (job["status"], job["historySaved"]) == ("succeeded", None)
    refused = client.get(BASE)
    assert (refused.status_code, refused.json()["code"]) == (403, "HISTORY_DISABLED")
    assert client.get("/api/v1/dr/jobs/gone").status_code == 404


def test_a_failed_save_does_not_fail_the_analysis(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def locked(_store: SqliteAnalysisStore, _record: AnalysisRecord) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(SqliteAnalysisStore, "save", locked)
    client = make_client()
    submitted = client.get("/api/v1/dr/analyze", params={"runbook": "runbooks/estimate-service.md"})
    job = client.get(f"/api/v1/dr/jobs/{submitted.json()['jobId']}", params={"wait": True}).json()
    assert (job["status"], job["historySaved"]) == ("succeeded", False)
    assert job["report"] is not None
    assert client.get(BASE).json()["items"] == []


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"riskLevel": "SEVERE"}, {"before": "yesterday"}]
)
def test_bad_queries_are_rejected(make_client: ClientFactory, params: dict[str, object]) -> None:
    response = make_client().get(BASE, params=params)
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


def test_service_history_and_the_next_report_use_stored_analyses(
    make_client: ClientFactory,
) -> None:
    client = make_client()
    first = client.get(f"/api/v1/dr/jobs/{_analyze(client)}").json()["report"]
    assert "historicalInsights" not in first  # nothing stored before it
    second = client.get(f"/api/v1/dr/jobs/{_analyze(client)}").json()["report"]
    insights = second["historicalInsights"]
    assert (insights["analysesConsidered"], insights["liveRuns"]) == (1, 0)
    history = client.get("/api/v1/services/Estimate Service/history").json()
    assert (history["serviceName"], history["analysesConsidered"]) == ("Estimate Service", 2)
    assert client.get("/api/v1/services/Nobody/history").json()["analysesConsidered"] == 0


def test_service_history_needs_the_knowledge_base(make_client: ClientFactory) -> None:
    client = make_client(knowledge_enabled=False)
    refused = client.get("/api/v1/services/S/history")
    assert (refused.status_code, refused.json()["code"]) == (403, "HISTORY_DISABLED")
    _analyze(client)
    second = client.get(f"/api/v1/dr/jobs/{_analyze(client)}").json()["report"]
    assert "historicalInsights" not in second  # stored, but not used
