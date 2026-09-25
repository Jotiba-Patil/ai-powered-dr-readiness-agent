"""Helpers for the execution API tests: an app with execution on, backed by the mock server."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from mcp import Client

from conftest import mock_checker
from dr_agent.api.app import create_app
from dr_agent.api.deps import AppState
from dr_agent.config import Settings
from dr_agent.llm.base import LLMProvider
from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.mock_mcp.state import Scenario

REPO = Path(__file__).resolve().parents[3]
SAMPLE = (REPO / "mock-data/runbooks/estimate-service-executable.md").read_text("utf-8")
BASE = "/api/v1/executions"
OPERATOR, APPROVERS = "Olivia", ("Ann", "Ben")
Json = dict[str, object]


@contextmanager
def execution_client(
    tmp_path: Path,
    scenario: Scenario | None = None,
    llm: LLMProvider | None = None,
    **overrides: object,
) -> Iterator[tuple[TestClient, DrEnvironment]]:
    env = DrEnvironment(scenario)
    server = build_server(env)
    values: dict[str, object] = {
        "llm_provider": "none",
        "execution_enabled": True,
        "execution_allow_live": True,
        "db_path": str(tmp_path / "dr-agent.db"),
        "execution_policy_file": str(REPO / "execution-policy.json"),
        **overrides,
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
    app = create_app(
        settings,
        llm=llm,
        checker=mock_checker(),
        mcp_factories={"drsim": lambda: Client(server)},
        execution_tick_seconds=3600,
    )
    with TestClient(app) as client:
        yield client, env


def settle(client: TestClient) -> None:
    """Waits for the background advance tasks the last requests started."""
    state = cast(AppState, client.app.state.dr)  # type: ignore[attr-defined]  # Starlette app
    assert state.execution is not None
    client.portal.call(state.execution.settle)  # type: ignore[union-attr]  # entered client


def analyze(client: TestClient, markdown: str = SAMPLE) -> str:
    """Runs a (rule-based) analysis and returns its finished job id."""
    submitted = client.post(
        "/api/v1/dr/analyze", json={"runbookMarkdown": markdown, "runbookName": "s.md"}
    )
    assert submitted.status_code == 202, submitted.text
    job_id = cast(str, submitted.json()["jobId"])
    done = client.get(f"/api/v1/dr/jobs/{job_id}", params={"wait": True}).json()
    assert done["status"] == "succeeded", done
    return job_id


def create(client: TestClient, mode: str = "live", markdown: str = SAMPLE) -> Json:
    response = client.post(
        BASE, json={"analysisJobId": analyze(client, markdown), "mode": mode, "startedBy": OPERATOR}
    )
    assert response.status_code == 201, response.text
    return cast(Json, response.json())


def step(execution: Json, number: int) -> Json:
    steps = cast(list[Json], execution["steps"])
    return next(s for s in steps if s["stepNumber"] == number)


def call_hash(execution: Json, number: int, kind: str = "call") -> str:
    return cast(str, cast(Json, step(execution, number)[kind])["callHash"])


def approve_all(client: TestClient, execution: Json) -> Json:
    for run in cast(list[Json], execution["steps"]):
        call = cast(Json, run["call"])
        needed = 2 if call["riskClass"] == "destructive" else 1
        for name in APPROVERS[:needed]:
            response = client.post(
                f"{BASE}/{execution['id']}/steps/{run['stepNumber']}/approve",
                json={"approver": name, "callHash": call["callHash"]},
            )
            assert response.status_code == 200, response.text
            execution = cast(Json, response.json())
    return execution


def act(
    client: TestClient, execution_id: object, path: str, body: Json | None = None
) -> Callable[[], Json]:
    """POSTs a decision, then returns a getter for the settled execution."""
    response = client.post(f"{BASE}/{execution_id}/{path}", json=body or {"actor": OPERATOR})
    assert response.status_code == 200, response.text

    def settled() -> Json:
        settle(client)
        return cast(Json, client.get(f"{BASE}/{execution_id}").json())

    return settled
