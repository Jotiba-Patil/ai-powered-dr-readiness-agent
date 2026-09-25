import json

import pytest
from conftest import ClientFactory, fake_llm, read_mock

from dr_agent.llm.disabled import DisabledProvider
from dr_agent.models.report import risk_level_from_score

ANALYZE = "/api/v1/dr/analyze"


def _files(runbook: str = "runbooks/payment-gateway.md", inventory: str | None = None) -> dict:
    files = {"runbook": (runbook.rsplit("/", 1)[-1], read_mock(runbook), "text/markdown")}
    if inventory:
        files["inventory"] = (
            inventory.rsplit("/", 1)[-1],
            read_mock(inventory),
            "application/json",
        )
    return files


def test_multipart_with_wait_returns_the_report(make_client: ClientFactory) -> None:
    client = make_client(fake_llm(risk_score=55))
    response = client.post(
        f"{ANALYZE}?wait=true", files=_files(inventory="inventories/partial-outage.json")
    )
    assert response.status_code == 200
    report = response.json()
    assert report["riskScore"] == 55
    assert report["riskLevel"] == risk_level_from_score(55).value
    assert report["meta"]["runbookFile"] == "payment-gateway.md"
    assert report["meta"]["inventoryFile"] == "partial-outage.json"
    assert report["aiAnalysisAvailable"] is True


def test_multipart_without_wait_returns_job_to_poll(make_client: ClientFactory) -> None:
    client = make_client()
    response = client.post(ANALYZE, files=_files())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] in {"pending", "running", "succeeded"}
    location = response.headers["location"]
    assert location == f"/api/v1/dr/jobs/{body['jobId']}"

    polled = client.get(f"{location}?wait=true").json()
    assert polled["status"] == "succeeded"
    assert polled["report"]["serviceSummary"]["name"] == "Payment Gateway"
    assert polled["error"] is None


def test_json_body_with_inline_inventory(make_client: ClientFactory) -> None:
    client = make_client()
    payload = {
        "runbookMarkdown": read_mock("runbooks/estimate-service.md").decode(),
        "inventory": json.loads(read_mock("inventories/healthy.json")),
        "runbookName": "../../etc/estimate.md",
    }
    response = client.post(f"{ANALYZE}?wait=true", json=payload)
    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["runbookFile"] == "estimate.md"  # directories stripped from client labels
    assert meta["inventoryFile"] == "request-body.json"


def test_llm_failure_degrades_gracefully(make_client: ClientFactory) -> None:
    client = make_client(DisabledProvider())
    response = client.post(f"{ANALYZE}?wait=true", files=_files())
    assert response.status_code == 200
    report = response.json()
    assert report["aiAnalysisAvailable"] is False
    assert "unavailable" in report["aiNote"]
    assert report["gapAnalysis"]  # rule-based gaps still present


def test_critical_risk_report(make_client: ClientFactory) -> None:
    client = make_client(fake_llm(risk_score=95))
    response = client.post(
        f"{ANALYZE}?wait=true",
        files=_files("runbooks/auth-service.md", "inventories/major-outage.json"),
    )
    assert response.json()["riskLevel"] == "CRITICAL"


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        (
            {"content": b"{not json", "headers": {"content-type": "application/json"}},
            400,
            "BAD_REQUEST",
        ),
        ({"content": b"hello", "headers": {"content-type": "text/plain"}}, 400, "BAD_REQUEST"),
        ({"json": {"inventory": None}}, 422, "VALIDATION_ERROR"),
        ({"json": {"runbookMarkdown": "# X", "extra": 1}}, 422, "VALIDATION_ERROR"),
        ({"json": {"runbookMarkdown": "# X\n\nno steps here"}}, 422, "PARSE_ERROR"),
        (
            {"json": {"runbookMarkdown": "# X", "inventory": {"services": [{"name": "a"}]}}},
            422,
            "VALIDATION_ERROR",
        ),
        ({"files": {"inventory": ("i.json", b"{}", "application/json")}}, 400, "BAD_REQUEST"),
        ({"files": {"runbook": ("r.md", b"\xff\xfe", "text/markdown")}}, 400, "BAD_REQUEST"),
        (
            {
                "files": {
                    "runbook": ("r.md", read_mock("runbooks/auth-service.md")),
                    "inventory": ("i.json", b"[1,", "application/json"),
                }
            },
            422,
            "VALIDATION_ERROR",
        ),
    ],
)
def test_bad_input_uses_shared_error_shape(
    make_client: ClientFactory, kwargs: dict, status: int, code: str
) -> None:
    response = make_client().post(ANALYZE, **kwargs)
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert isinstance(body["error"], str)
    assert set(body) <= {"error", "code", "details"}


def test_oversized_json_body_is_rejected(make_client: ClientFactory) -> None:
    client = make_client(api_max_upload_bytes=1024)
    response = client.post(ANALYZE, json={"runbookMarkdown": "x" * 4096})
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_oversized_upload_is_rejected(make_client: ClientFactory) -> None:
    client = make_client(api_max_upload_bytes=100)
    response = client.post(ANALYZE, files=_files())
    assert response.status_code == 413


def test_get_analyze_reads_allow_listed_files(make_client: ClientFactory) -> None:
    client = make_client()
    response = client.get(
        ANALYZE,
        params={
            "runbook": "runbooks/auth-service.md",
            "inventory": "inventories/major-outage.json",
            "wait": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["meta"]["runbookFile"] == "runbooks/auth-service.md"


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({"runbook": "../README.md"}, 403, "PATH_NOT_ALLOWED"),
        ({"runbook": "../../../../etc/passwd.md"}, 403, "PATH_NOT_ALLOWED"),
        ({"runbook": "inventories/healthy.json"}, 403, "PATH_NOT_ALLOWED"),
        (
            {"runbook": "runbooks/auth-service.md", "inventory": "../pyproject.json"},
            403,
            "PATH_NOT_ALLOWED",
        ),
        ({"runbook": "runbooks/missing.md"}, 404, "NOT_FOUND"),
        ({}, 422, "VALIDATION_ERROR"),
    ],
)
def test_get_analyze_rejects_bad_paths(
    make_client: ClientFactory, params: dict, status: int, code: str
) -> None:
    response = make_client().get(ANALYZE, params=params)
    assert response.status_code == status
    assert response.json()["code"] == code
