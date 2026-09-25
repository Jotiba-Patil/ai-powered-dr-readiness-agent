"""The simulated DR environment: the outage scenario, tool effects, faults and scenario files."""

import json
from pathlib import Path

import pytest

from dr_agent.mock_mcp.environment import DrEnvironment, SimulatedFailureError
from dr_agent.mock_mcp.state import Scenario, ToolFault, load_scenario
from dr_agent.utils.errors import ConfigError


def test_default_state_is_the_regional_outage() -> None:
    env = DrEnvironment()
    assert env.rollout_status("estimate-service", "primary", None)["ready"] is False
    assert env.db_is_in_recovery("estimate-postgres", None) == {
        "cluster": "estimate-postgres",
        "inRecovery": True,
    }
    with pytest.raises(SimulatedFailureError, match="cold"):
        env.cache_ping("pricing-cache")
    with pytest.raises(SimulatedFailureError, match="cachesWarm, databasesPrimary"):
        env.smoke_run("estimate-service", "standby")


def test_full_failover_makes_the_smoke_test_pass() -> None:
    env = DrEnvironment()
    assert env.rollout_restart("estimate-service", "standby")["revision"] == 8
    env.rollout_status("estimate-service", "standby", True)
    env.db_promote_replica("estimate-postgres")
    env.db_is_in_recovery("estimate-postgres", False)
    env.cache_warm("pricing-cache", "latest")
    assert env.cache_ping("pricing-cache")["pong"] is True
    assert env.dns_switch("estimate-service", "standby")["previous"] == "primary"
    result = env.smoke_run("estimate-service", "standby")
    assert result["passed"] is True


def test_expectations_and_invalid_operations_fail() -> None:
    env = DrEnvironment()
    with pytest.raises(SimulatedFailureError, match="expected ready=True, found 0/3 ready"):
        env.rollout_status("estimate-service", "standby", True)
    with pytest.raises(SimulatedFailureError, match="expected in_recovery=False"):
        env.db_is_in_recovery("estimate-postgres", False)
    with pytest.raises(SimulatedFailureError, match="no previous revision"):
        env.rollout_undo("estimate-service", "standby")
    env.db_promote_replica("estimate-postgres")
    with pytest.raises(SimulatedFailureError, match="already the primary"):
        env.db_promote_replica("estimate-postgres")
    with pytest.raises(SimulatedFailureError, match="unknown snapshot"):
        env.cache_warm("pricing-cache", "yesterday")
    for call in (
        lambda: env.rollout_status("nope", "primary", None),
        lambda: env.db_is_in_recovery("nope", None),
        lambda: env.cache_ping("nope"),
        lambda: env.dns_switch("nope", "standby"),
    ):
        with pytest.raises(SimulatedFailureError, match="unknown"):
            call()


def test_undo_restores_the_previous_revision() -> None:
    env = DrEnvironment()
    env.rollout_restart("estimate-service", "standby")
    undone = env.rollout_undo("estimate-service", "standby")
    assert (undone["revision"], undone["ready"]) == (7, False)


async def test_faults_hooks_and_call_counts() -> None:
    env = DrEnvironment(
        Scenario(faults={"db_promote_replica": ToolFault(fail_on_calls=[1], message="lag")})
    )
    seen: list[str] = []

    async def hook(tool: str) -> None:
        seen.append(tool)

    env.before_call = hook
    with pytest.raises(SimulatedFailureError, match="lag"):
        await env.enter("db_promote_replica")
    await env.enter("db_promote_replica")  # second call passes
    await env.enter("cache_ping")
    assert env.call_counts == {"db_promote_replica": 2, "cache_ping": 1}
    assert seen == ["db_promote_replica", "db_promote_replica", "cache_ping"]
    assert ToolFault(fail_always=True).fails(99)


async def test_latency_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("dr_agent.mock_mcp.environment.asyncio.sleep", fake_sleep)
    env = DrEnvironment(Scenario(faults={"smoke_run": ToolFault(latency_ms=250)}))
    await env.enter("smoke_run")
    assert delays == [0.25]


def test_scenario_file(tmp_path: Path) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(
        json.dumps(
            {
                "state": {"dns": {"estimate-service": "standby"}},
                "faults": {"smoke_run": {"failAlways": True, "message": "red"}},
            }
        ),
        encoding="utf-8",
    )
    scenario = load_scenario(path)
    assert scenario.state.dns == {"estimate-service": "standby"}
    assert scenario.state.databases["estimate-postgres"].primary is False  # defaults kept
    assert scenario.faults["smoke_run"].fail_always


@pytest.mark.parametrize(
    ("content", "match"),
    [(None, "cannot be read"), ("{nope", "not valid JSON"), ('{"faults": 3}', "is invalid")],
)
def test_bad_scenario_files(tmp_path: Path, content: str | None, match: str) -> None:
    path = tmp_path / "scenario.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=match):
        load_scenario(path)


def test_shipped_scenarios_load() -> None:
    folder = Path(__file__).resolve().parents[3] / "mock-data" / "scenarios"
    files = sorted(folder.glob("*.json"))
    assert [f.name for f in files] == ["slow-promotion.json", "smoke-fails-once.json"]
    for path in files:
        assert load_scenario(path).faults
