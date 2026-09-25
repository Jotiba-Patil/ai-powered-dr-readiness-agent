"""Phase 10 exit: the engine runs the executable sample against the mock MCP server.

Real `McpToolExecutor` over the SDK's in-memory client, the repo's default
`execution-policy.json`, and a SQLite store in `tmp_path`.
"""

import asyncio
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import Client

from dr_agent.core.parser import parse_runbook
from dr_agent.execution.decisions import Approve, ReportOutcome
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import (
    CallKind,
    Execution,
    ExecutionMode,
    ExecutionState,
    StepState,
)
from dr_agent.execution.policy_file import load_policy
from dr_agent.execution.recovery import recover_interrupted
from dr_agent.execution.session import ExecutionLimits
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.mock_mcp.state import Scenario, ToolFault
from dr_agent.tools.mcp_executor import McpToolExecutor

REPO = Path(__file__).resolve().parents[3]
OPERATOR, APPROVERS = "Olivia", ("Ann", "Ben")


@asynccontextmanager
async def drill(
    tmp_path: Path, env: DrEnvironment
) -> AsyncIterator[tuple[ExecutionEngine, SqliteExecutionStore, Execution]]:
    server = build_server(env)
    store = await SqliteExecutionStore.open(tmp_path / "executions.db")
    async with McpToolExecutor({"drsim": lambda: Client(server)}, rng=random.Random(0)) as ex:
        engine = ExecutionEngine(
            store=store,
            executor=ex,
            policy=load_policy(REPO / "execution-policy.json"),
            limits=ExecutionLimits(enabled=True, allow_live=True),
        )
        runbook = parse_runbook(
            (REPO / "mock-data/runbooks/estimate-service-executable.md").read_text("utf-8")
        )
        execution = await engine.create(
            runbook, mode=ExecutionMode.LIVE, started_by=OPERATOR, runbook_label="sample"
        )
        for run in execution.steps:
            assert run.call is not None
            assert run.state is StepState.AWAITING_APPROVAL, run.policy_errors
            needed = 2 if run.call.risk_class and run.call.risk_class.value == "destructive" else 1
            for name in APPROVERS[:needed]:
                execution = await engine.decide(
                    execution.id, run.step_number, Approve(name, run.call.call_hash)
                )
        await engine.start(execution.id, OPERATOR)
        yield engine, store, execution


def hold(env: DrEnvironment, tool: str) -> tuple[asyncio.Event, asyncio.Event]:
    """Holds the first call of `tool` inside the server until `release` is set."""
    started, release = asyncio.Event(), asyncio.Event()

    async def before_call(name: str) -> None:
        if name == tool and not started.is_set():
            started.set()
            await release.wait()

    env.before_call = before_call
    return started, release


async def confirm_step_1(engine: ExecutionEngine, execution_id: str) -> None:
    await engine.decide(execution_id, 1, ReportOutcome("Ann", True, "primary is down"))


async def test_failover_end_to_end(tmp_path: Path) -> None:
    env = DrEnvironment()
    async with drill(tmp_path, env) as (engine, _, execution):
        execution = await engine.advance(execution.id)
        assert execution.step(1).state is StepState.VERIFYING  # no verify tool: a person confirms
        await confirm_step_1(engine, execution.id)
        execution = await engine.advance(execution.id)
        assert execution.state is ExecutionState.COMPLETED
        assert all(run.state is StepState.SUCCEEDED for run in execution.steps)
        events, chain = await engine.audit(execution.id)
        assert chain.valid
    assert env.state.dns["estimate-service"] == "standby"
    assert env.state.databases["estimate-postgres"].primary
    assert env.state.caches["pricing-cache"].warm
    smoke = execution.step(5).verify
    assert smoke is not None
    assert smoke.result is not None
    assert smoke.result.structured == {
        "service": "estimate-service",
        "region": "standby",
        "passed": True,
        "checks": {
            "dnsPointsToRegion": True,
            "deploymentReady": True,
            "databasesPrimary": True,
            "cachesWarm": True,
        },
    }
    assert sum(env.call_counts.values()) == 9 == execution.tool_calls_used
    assert len(events) > 20


async def test_injected_failure_then_rollback(tmp_path: Path) -> None:
    env = DrEnvironment(
        Scenario(faults={"smoke_run": ToolFault(fail_on_calls=[1], message="checkout 500s")})
    )
    async with drill(tmp_path, env) as (engine, _, execution):
        await engine.advance(execution.id)
        await confirm_step_1(engine, execution.id)
        execution = await engine.advance(execution.id)
        step5 = execution.step(5)
        assert step5.state is StepState.FAILED
        assert step5.summary is not None
        assert "checkout 500s" in step5.summary
        assert execution.state is ExecutionState.PAUSED
        assert env.state.dns["estimate-service"] == "standby"

        assert step5.rollback is not None
        for name in APPROVERS:  # dns_switch_region is destructive: two people
            await engine.decide(
                execution.id, 5, Approve(name, step5.rollback.call_hash, kind=CallKind.ROLLBACK)
            )
        execution = await engine.rollback(execution.id, 5, OPERATOR)
        assert execution.step(5).state is StepState.ROLLED_BACK
        assert env.state.dns["estimate-service"] == "primary"
        closed = await engine.close(execution.id, OPERATOR, "failover abandoned")
        assert closed.state is ExecutionState.FAILED
        assert (await engine.audit(execution.id))[1].valid


async def test_abort_mid_call(tmp_path: Path) -> None:
    env = DrEnvironment()
    started, release = hold(env, "db_promote_replica")
    async with drill(tmp_path, env) as (engine, _, execution):
        await engine.advance(execution.id)
        await confirm_step_1(engine, execution.id)
        task = asyncio.create_task(engine.advance(execution.id))
        await started.wait()
        aborted = await engine.abort(execution.id, OPERATOR, "wrong incident")
        assert aborted.step(3).state is StepState.UNKNOWN
        release.set()
        final = await task
    assert final.state is ExecutionState.ABORTED
    assert final.step(3).state is StepState.UNKNOWN
    assert env.state.databases["estimate-postgres"].primary  # the call did run: hence UNKNOWN
    assert env.call_counts["cache_warm_from_snapshot"] == 0  # nothing ran after the abort


async def test_restart_recovery(tmp_path: Path) -> None:
    env = DrEnvironment()
    started, release = hold(env, "db_promote_replica")
    async with drill(tmp_path, env) as (engine, store, execution):
        await engine.advance(execution.id)
        await confirm_step_1(engine, execution.id)
        task = asyncio.create_task(engine.advance(execution.id))
        await started.wait()
        # A new process starting up sees the call in flight and cannot know its outcome.
        assert await recover_interrupted(store, lambda: execution.created_at) == [execution.id]
        recovered = await store.get(execution.id)
        assert recovered.step(3).state is StepState.UNKNOWN
        assert recovered.state is ExecutionState.PAUSED
        release.set()
        await task  # the old call's result is only recorded

        await engine.decide(execution.id, 3, ReportOutcome("Priya", True, "replica is primary"))
        await engine.resume(execution.id, OPERATOR)
        execution = await engine.advance(execution.id)
        assert execution.state is ExecutionState.COMPLETED
        assert env.call_counts["db_promote_replica"] == 1  # never re-sent
        assert (await engine.audit(execution.id))[1].valid
