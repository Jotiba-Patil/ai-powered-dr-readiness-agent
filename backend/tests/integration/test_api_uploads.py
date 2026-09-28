"""Saved runbook uploads through the API, and the HTML export in the reader's timezone."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from schedule_api_support import SCHEDULES, run_now, schedule_client

from conftest import MOCK, ClientFactory

UPLOAD = "/api/v1/dr/samples/runbooks"
RUNBOOK = (MOCK / "runbooks" / "estimate-service.md").read_text(encoding="utf-8")


def allowed_dir(tmp_path: Path) -> Path:
    """A copy of the sample folder, so uploads never touch the repository."""
    base = tmp_path / "allowed"
    shutil.copytree(MOCK / "runbooks", base / "runbooks")
    shutil.copytree(MOCK / "inventories", base / "inventories")
    return base


def test_json_and_multipart_uploads_are_saved_and_listed(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    base = allowed_dir(tmp_path)
    client = make_client(api_allowed_dir=str(base))
    saved = client.post(UPLOAD, json={"fileName": "My Runbook.md", "markdown": RUNBOOK})
    assert saved.status_code == 201, saved.text
    assert saved.json() == {"path": "uploads/my-runbook.md", "serviceName": "Estimate Service"}
    files = {"file": ("my-runbook.md", RUNBOOK.encode(), "text/markdown")}
    again = client.post(UPLOAD, files=files)
    assert again.json()["path"] == "uploads/my-runbook-2.md"
    listed = client.get("/api/v1/dr/samples").json()["runbooks"]
    assert {"uploads/my-runbook.md", "uploads/my-runbook-2.md"} <= set(listed)
    assert (base / "uploads" / "my-runbook.md").read_text(encoding="utf-8") == RUNBOOK  # exact
    text = client.get("/api/v1/dr/samples/file", params={"path": "uploads/my-runbook.md"})
    assert text.json()["content"] == RUNBOOK.strip()  # the samples API trims, as for all samples
    analyzed = client.get("/api/v1/dr/analyze", params={"runbook": "uploads/my-runbook.md"})
    assert analyzed.status_code == 202


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"fileName": "x.md", "markdown": "no runbook here"}, 422, "PARSE_ERROR"),
        ({"fileName": "x.json", "markdown": RUNBOOK}, 400, "BAD_REQUEST"),
        ({"fileName": "x.md"}, 422, "VALIDATION_ERROR"),
        ({"fileName": "x.md", "markdown": RUNBOOK + "x" * 70_000}, 413, "PAYLOAD_TOO_LARGE"),
    ],
)
def test_bad_uploads_are_refused(
    make_client: ClientFactory, tmp_path: Path, body: dict[str, str], status: int, code: str
) -> None:
    base = allowed_dir(tmp_path)
    client = make_client(api_allowed_dir=str(base))
    response = client.post(UPLOAD, json=body)
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert not (base / "uploads").exists() or not list((base / "uploads").iterdir())


def test_other_bodies_and_limits(make_client: ClientFactory, tmp_path: Path) -> None:
    base = allowed_dir(tmp_path)
    client = make_client(api_allowed_dir=str(base), runbook_upload_max_files=1)
    latin1 = {"file": ("x.md", "é".encode("latin-1"), "text/markdown")}
    assert client.post(UPLOAD, files=latin1).status_code == 400  # not UTF-8
    assert (
        client.post(UPLOAD, content=b"x", headers={"content-type": "text/plain"}).status_code == 400
    )
    assert client.post(UPLOAD, files={"other": ("x.md", b"x")}).status_code == 400
    assert client.post(UPLOAD, json={"fileName": "a.md", "markdown": RUNBOOK}).status_code == 201
    full = client.post(UPLOAD, json={"fileName": "b.md", "markdown": RUNBOOK})
    assert (full.status_code, full.json()["code"]) == (409, "CONFLICT")


def test_uploads_can_be_turned_off(make_client: ClientFactory, tmp_path: Path) -> None:
    client = make_client(api_allowed_dir=str(allowed_dir(tmp_path)), runbook_uploads_enabled=False)
    response = client.post(UPLOAD, json={"fileName": "a.md", "markdown": RUNBOOK})
    assert (response.status_code, response.json()["code"]) == (403, "UPLOADS_DISABLED")


def test_a_schedule_runs_an_uploaded_runbook(tmp_path: Path) -> None:
    base = allowed_dir(tmp_path)
    with schedule_client(tmp_path, api_allowed_dir=str(base)) as (client, _):
        path = client.post(UPLOAD, json={"fileName": "drill.md", "markdown": RUNBOOK}).json()[
            "path"
        ]
        body = {
            "name": "Monthly drill",
            "runbookPath": path,
            "cadence": {"kind": "monthly", "day": 31, "time": "06:00"},
            "timezone": "Asia/Kolkata",
            "createdBy": "Alice",
        }
        created = client.post(SCHEDULES, json=body).json()
        assert created["description"] == (
            "Monthly on day 31 (last day in shorter months) 06:00 Asia/Kolkata"
        )
        run = run_now(client, created["id"])
        assert run["state"] == "succeeded", run


def test_html_export_in_the_readers_timezone(make_client: ClientFactory) -> None:
    client = make_client()
    params = {"runbook": "runbooks/estimate-service.md", "wait": True}
    job = client.get("/api/v1/dr/analyze", params=params).json()
    job_id = job["meta"] and client.get("/api/v1/analyses").json()["items"][0]["id"]
    utc = client.get(f"/api/v1/dr/jobs/{job_id}/report.html").text
    assert "UTC</p>" in utc
    kolkata = client.get(f"/api/v1/analyses/{job_id}/report.html", params={"tz": "Asia/Kolkata"})
    assert "UTC+05:30</p>" in kolkata.text
    bad = client.get(f"/api/v1/dr/jobs/{job_id}/report.html", params={"tz": "Mars/Olympus"})
    assert (bad.status_code, bad.json()["code"]) == (422, "VALIDATION_ERROR")
