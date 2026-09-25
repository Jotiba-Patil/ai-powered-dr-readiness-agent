"""The frontend's committed OpenAPI schema must match the app (regenerate: `uv run poe gen-api`)."""

import json
from pathlib import Path

from dr_agent.api.export_openapi import build_openapi_json, main

REPO = Path(__file__).resolve().parents[3]
COMMITTED = REPO / "frontend" / "openapi.json"


def test_committed_schema_is_current() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == build_openapi_json(), (
        "frontend/openapi.json is stale: run `uv run poe gen-api`"
    )


def test_schema_documents_dashboard_routes() -> None:
    paths = json.loads(build_openapi_json())["paths"]
    for path in (
        "/api/v1/dr/analyze",
        "/api/v1/dr/jobs/{job_id}",
        "/api/v1/dr/jobs/{job_id}/report.html",
        "/api/v1/dr/samples",
        "/api/v1/dr/samples/file",
    ):
        assert path in paths


def test_main_writes_the_schema(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    assert main([str(target)]) == 0
    assert target.read_text(encoding="utf-8") == build_openapi_json()


def test_main_requires_one_argument() -> None:
    assert main([]) == 1
