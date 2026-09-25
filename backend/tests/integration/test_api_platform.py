import pytest

from conftest import BlockingProvider, ClientFactory, read_mock
from dr_agent import __version__
from dr_agent.api.deps import AppState
from dr_agent.api.schemas import JobState

ANALYZE = "/api/v1/dr/analyze"
RUNBOOK = {"runbook": ("r.md", read_mock("runbooks/estimate-service.md"), "text/markdown")}


def test_health_endpoint(make_client: ClientFactory) -> None:
    response = make_client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "uptime": 0.0}


def test_security_headers_on_every_response(make_client: ClientFactory) -> None:
    client = make_client()
    for response in (client.get("/api/v1/health"), client.get("/api/v1/dr/jobs/nope")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_request_id_is_echoed_when_safe(make_client: ClientFactory) -> None:
    response = make_client().get(
        "/api/v1/health", headers={"X-Request-ID": "abc-123", "X-Correlation-ID": "corr.9"}
    )
    assert response.headers["x-request-id"] == "abc-123"
    assert response.headers["x-correlation-id"] == "corr.9"


def test_unsafe_request_id_is_replaced(make_client: ClientFactory) -> None:
    response = make_client().get("/api/v1/health", headers={"X-Request-ID": "bad id<script>"})
    generated = response.headers["x-request-id"]
    assert generated != "bad id<script>"
    assert len(generated) == 32
    assert response.headers["x-correlation-id"] == generated


def test_cors_preflight_for_configured_origin(make_client: ClientFactory) -> None:
    client = make_client(cors_origins="http://localhost:5173")
    response = client.options(
        ANALYZE,
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("get", "/nope", 404, "NOT_FOUND"),
        ("delete", "/api/v1/health", 405, "METHOD_NOT_ALLOWED"),
        ("get", "/api/v1/dr/jobs/unknown", 404, "NOT_FOUND"),
        ("get", "/api/v1/dr/jobs/bad%20id", 422, "VALIDATION_ERROR"),
    ],
)
def test_framework_errors_use_shared_shape(
    make_client: ClientFactory, method: str, path: str, status: int, code: str
) -> None:
    response = getattr(make_client(), method)(path)
    assert response.status_code == status
    assert response.json()["code"] == code


def test_unhandled_route_error_is_a_generic_500(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(_markdown: str) -> None:
        raise RuntimeError("secret internals")

    monkeypatch.setattr("dr_agent.api.routes.parse_markdown", explode)
    response = make_client(raise_server_exceptions=False).post(ANALYZE, files=RUNBOOK)
    assert response.status_code == 500
    assert response.json() == {"error": "internal server error", "code": "INTERNAL_ERROR"}


def test_failed_job_reports_internal_error(make_client: ClientFactory) -> None:
    class Exploding:
        async def generate(self, **_kwargs: object) -> str:
            raise RuntimeError("boom")

    response = make_client(Exploding()).post(f"{ANALYZE}?wait=true", files=RUNBOOK)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "INTERNAL_ERROR"


def test_capacity_limit_returns_429(make_client: ClientFactory) -> None:
    client = make_client(BlockingProvider(), api_max_stored_jobs=1)
    assert client.post(ANALYZE, files=RUNBOOK).status_code == 202
    response = client.post(ANALYZE, files=RUNBOOK)
    assert response.status_code == 429
    assert response.json()["code"] == "CAPACITY_EXCEEDED"


def test_shutdown_cancels_running_jobs(make_client: ClientFactory) -> None:
    client = make_client(BlockingProvider(), api_wait_timeout_seconds=0.05)
    body = client.post(f"{ANALYZE}?wait=true", files=RUNBOOK).json()
    assert body["status"] == "running"
    state = client.app.state.dr  # type: ignore[attr-defined]
    assert isinstance(state, AppState)
    client.__exit__(None, None, None)  # lifespan shutdown
    job = state.jobs.get(body["jobId"])
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert job.error.code == "CANCELLED"


def test_openapi_documents_both_body_types(make_client: ClientFactory) -> None:
    spec = make_client().get("/openapi.json").json()
    body = spec["paths"][ANALYZE]["post"]["requestBody"]["content"]
    assert set(body) == {"application/json", "multipart/form-data"}
    schemas = spec["components"]["schemas"]
    assert "AnalyzeJsonRequest" in schemas
    assert "SystemInventory" in schemas
    assert set(spec["paths"]) == {
        "/api/v1/health",
        ANALYZE,
        "/api/v1/dr/jobs/{job_id}",
        "/api/v1/dr/jobs/{job_id}/report.html",
        "/api/v1/dr/samples",
        "/api/v1/dr/samples/file",
        "/api/v1/execution/settings",
        "/api/v1/tools",
        "/api/v1/executions",
        "/api/v1/executions/{execution_id}",
        "/api/v1/executions/{execution_id}/{action}",
        "/api/v1/executions/{execution_id}/audit",
        "/api/v1/analyses",
        "/api/v1/analyses/{analysis_id}",
        "/api/v1/analyses/{analysis_id}/runbook",
        "/api/v1/analyses/{analysis_id}/report.html",
        "/api/v1/analyses/{analysis_id}/executions",
        "/api/v1/analyses/{analysis_id}/executions/{execution_id}",
        "/api/v1/services/{service_name}/history",
        "/api/v1/executions/{execution_id}/steps/{step_number}/call",
        "/api/v1/executions/{execution_id}/steps/{step_number}/approve",
        "/api/v1/executions/{execution_id}/steps/{step_number}/{action}",
    }
