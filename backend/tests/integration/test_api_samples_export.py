"""Dashboard support routes: sample picker and HTML report export."""

import pytest

from conftest import BlockingProvider, ClientFactory, fake_llm, read_mock

SAMPLES = "/api/v1/dr/samples"


def test_lists_mock_runbooks_and_inventories(make_client: ClientFactory) -> None:
    body = make_client().get(SAMPLES).json()
    assert body["runbooks"] == [
        "runbooks/auth-service.md",
        "runbooks/estimate-service-executable.md",
        "runbooks/estimate-service.md",
        "runbooks/order-service.md",
        "runbooks/payment-gateway.md",
    ]
    assert body["inventories"] == [
        "inventories/healthy.json",
        "inventories/major-outage.json",
        "inventories/order-service.json",
        "inventories/partial-outage.json",
    ]


def test_missing_sample_folders_give_empty_lists(make_client: ClientFactory, tmp_path) -> None:
    body = make_client(api_allowed_dir=str(tmp_path)).get(SAMPLES).json()
    assert body == {"runbooks": [], "inventories": []}


def test_reads_one_sample_file(make_client: ClientFactory) -> None:
    response = make_client().get(f"{SAMPLES}/file", params={"path": "runbooks/auth-service.md"})
    assert response.status_code == 200
    assert response.json()["path"] == "runbooks/auth-service.md"
    assert response.json()["content"].startswith("# ")


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("../pyproject.toml", 403, "PATH_NOT_ALLOWED"),
        ("runbooks/../../README.md", 403, "PATH_NOT_ALLOWED"),
        ("expected-reports/nope.txt", 403, "PATH_NOT_ALLOWED"),
        ("runbooks/missing.md", 404, "NOT_FOUND"),
    ],
)
def test_sample_file_is_allow_listed(
    make_client: ClientFactory, path: str, status: int, code: str
) -> None:
    response = make_client().get(f"{SAMPLES}/file", params={"path": path})
    assert response.status_code == status
    assert response.json()["code"] == code


def test_exports_finished_report_as_html(make_client: ClientFactory) -> None:
    client = make_client(fake_llm(risk_score=30))
    created = client.post(
        "/api/v1/dr/analyze",
        json={"runbookMarkdown": "# Svc\n\n## Recovery Steps\n1. Restart <b>it</b>"},
    ).json()
    client.get(f"/api/v1/dr/jobs/{created['jobId']}?wait=true")

    response = client.get(f"/api/v1/dr/jobs/{created['jobId']}/report.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment" in response.headers["content-disposition"]
    assert "<b>it</b>" not in response.text  # untrusted runbook text is escaped
    csp = response.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src" not in csp  # no scripts at all: default-src 'none' covers them


def test_html_export_of_unfinished_job_is_a_conflict(make_client: ClientFactory) -> None:
    client = make_client(BlockingProvider())
    markdown = read_mock("runbooks/estimate-service.md").decode()
    job_id = client.post("/api/v1/dr/analyze", json={"runbookMarkdown": markdown}).json()["jobId"]
    response = client.get(f"/api/v1/dr/jobs/{job_id}/report.html")
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_html_export_of_unknown_job_is_not_found(make_client: ClientFactory) -> None:
    response = make_client().get("/api/v1/dr/jobs/nope/report.html")
    assert response.status_code == 404
