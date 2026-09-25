"""Shared helpers for the execution tests: the drsim catalog and policy, a clock, an engine."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import JsonValue

from dr_agent.core.parser import parse_runbook
from dr_agent.execution.decisions import Approve
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import Execution, StepState
from dr_agent.execution.policy_file import ExecutionPolicy, parse_policy
from dr_agent.execution.proposer import ToolProposer
from dr_agent.execution.session import ExecutionLimits
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.models.runbook import Runbook
from dr_agent.tools.base import ToolExecutor, ToolSpec
from dr_agent.tools.fake import FakeExecutor

REPO_ROOT = Path(__file__).resolve().parents[3]
OPERATOR = "Olivia"
APPROVERS = ("Ann", "Ben")

_REGION: dict[str, JsonValue] = {"type": "string", "enum": ["primary", "standby"]}
_STR: dict[str, JsonValue] = {"type": "string", "minLength": 1}
_FLAG: dict[str, JsonValue] = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}
# tool -> (required properties, optional properties, readOnlyHint, destructiveHint, policy risk).
# Mirrors the bundled mock MCP server; test_mock_mcp_server.py checks they stay in sync.
DRSIM: dict[str, tuple[dict[str, JsonValue], dict[str, JsonValue], bool, bool, str]] = {
    "k8s_rollout_status": (
        {"deployment": _STR, "region": _REGION},
        {"expect_ready": _FLAG},
        True,
        False,
        "read",
    ),
    "k8s_rollout_restart": ({"deployment": _STR, "region": _REGION}, {}, False, False, "write"),
    "k8s_rollout_undo": ({"deployment": _STR, "region": _REGION}, {}, False, False, "write"),
    "db_is_in_recovery": ({"cluster": _STR}, {"expect_in_recovery": _FLAG}, True, False, "read"),
    "db_promote_replica": ({"cluster": _STR}, {}, False, True, "destructive"),
    "cache_ping": ({"cache": _STR}, {}, True, False, "read"),
    "cache_warm_from_snapshot": ({"cache": _STR, "snapshot": _STR}, {}, False, False, "write"),
    "dns_switch_region": ({"service": _STR, "region": _REGION}, {}, False, True, "destructive"),
    "smoke_run": ({"service": _STR, "region": _REGION}, {}, True, False, "read"),
}


def drsim_catalog() -> list[ToolSpec]:
    return [
        ToolSpec(
            server="drsim",
            name=name,
            description=f"simulated {name}",
            input_schema={
                "type": "object",
                "properties": required | optional,
                "required": sorted(required),
                "additionalProperties": False,
            },
            read_only_hint=read_only,
            destructive_hint=destructive,
        )
        for name, (required, optional, read_only, destructive, _risk) in DRSIM.items()
    ]


def drsim_policy_dict() -> dict[str, JsonValue]:
    tools: dict[str, JsonValue] = {name: {"risk": risk} for name, (*_, risk) in DRSIM.items()}
    tools["dns_switch_region"] = {
        "risk": "destructive",
        "constraints": {"region": {"enum": ["primary", "standby"]}},
    }
    return {"servers": {"drsim": {"tools": tools}}}


def drsim_policy() -> ExecutionPolicy:
    return parse_policy(json.dumps(drsim_policy_dict()))


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: float) -> None:
        self.now += timedelta(minutes=minutes)


def executable_runbook() -> Runbook:
    path = REPO_ROOT / "mock-data" / "runbooks" / "estimate-service-executable.md"
    return parse_runbook(path.read_text(encoding="utf-8"))


def limits(**overrides: object) -> ExecutionLimits:
    return replace(ExecutionLimits(enabled=True, allow_live=True), **overrides)


async def make_engine(
    tmp_path: Path,
    executor: ToolExecutor | None = None,
    *,
    policy: ExecutionPolicy | None = None,
    clock: Clock | None = None,
    proposer: ToolProposer | None = None,
    **limit_overrides: object,
) -> tuple[ExecutionEngine, SqliteExecutionStore, Clock]:
    store = await SqliteExecutionStore.open(tmp_path / "executions.db")
    clock = clock or Clock()
    ids = iter(f"exec-{n}" for n in range(1, 100))
    engine = ExecutionEngine(
        store=store,
        executor=executor or FakeExecutor(drsim_catalog()),
        policy=policy or drsim_policy(),
        limits=limits(**limit_overrides),
        clock=clock,
        id_factory=lambda: next(ids),
        proposer=proposer,
    )
    return engine, store, clock


async def approve_waiting(engine: ExecutionEngine, execution: Execution) -> Execution:
    """Gives every step awaiting approval the approvals its risk class needs."""
    for run in execution.steps:
        if run.state is not StepState.AWAITING_APPROVAL or run.call is None:
            continue
        needed = 2 if run.call.risk_class and run.call.risk_class.value == "destructive" else 1
        for approver in APPROVERS[:needed]:
            execution = await engine.decide(
                execution.id, run.step_number, Approve(approver, run.call.call_hash)
            )
    return execution
