"""Engine failure paths: failed calls, rollback, retry, verify failure, timeouts, limits."""

import asyncio
import json
from pathlib import Path

import pytest
from exec_support import (
    OPERATOR,
    approve_waiting,
    drsim_catalog,
    drsim_policy_dict,
    executable_runbook,
    make_engine,
)

from dr_agent.execution.decisions import Approve, ReportOutcome, Retry, Skip
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import CallKind, Execution, ExecutionMode, ExecutionState, StepState
from dr_agent.execution.policy_file import parse_policy
from dr_agent.tools.base import ToolResult
from dr_agent.tools.fake import FakeExecutor
from dr_agent.utils.errors import InvalidTransitionError, PolicyViolationError, ToolError


async def _started(
    tmp_path: Path, executor: FakeExecutor, **limits: object
) -> tuple[ExecutionEngine, Execution]:
    engine, _, _ = await make_engine(tmp_path, executor, **limits)
    execution = await engine.create(
        executable_runbook(), mode=ExecutionMode.LIVE, started_by=OPERATOR, runbook_label="s"
    )
    execution = await approve_waiting(engine, execution)
    await engine.start(execution.id, OPERATOR)
    return engine, execution


def _fake() -> FakeExecutor:
    return FakeExecutor(drsim_catalog())


async def test_failed_call_pauses_and_rollback_needs_its_own_approval(tmp_path: Path) -> None:
    executor = _fake()
    executor.script("drsim", "k8s_rollout_restart", ToolResult(ok=False, content="crashloop"))
    engine, execution = await _started(tmp_path, executor)
    execution = await engine.advance(execution.id)
    step = execution.step(2)
    assert (step.state, step.summary) == (StepState.FAILED, "crashloop")
    assert (execution.state, execution.pause_reason) == (ExecutionState.PAUSED, "step 2 failed")

    with pytest.raises(PolicyViolationError, match="needs its approvals"):
        await engine.rollback(execution.id, 2, OPERATOR)
    with pytest.raises(InvalidTransitionError, match="failed step with a rollback"):
        await engine.rollback(execution.id, 1, OPERATOR)
    assert step.rollback is not None
    await engine.decide(
        execution.id, 2, Approve("Ann", step.rollback.call_hash, kind=CallKind.ROLLBACK)
    )
    execution = await engine.rollback(execution.id, 2, OPERATOR)
    assert execution.step(2).state is StepState.ROLLED_BACK
    assert executor.calls[-1][1] == "k8s_rollout_undo"

    # Step 5 depends on the rolled-back step 2, so it must be skipped to finish.
    await engine.resume(execution.id, OPERATOR)
    await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "confirmed"))
    execution = await engine.advance(execution.id)
    assert execution.step(4).state is StepState.SUCCEEDED
    assert execution.step(5).state is StepState.APPROVED
    await engine.decide(execution.id, 5, Skip("Ann", "restart rolled back; failover abandoned"))
    execution = await engine.advance(execution.id)
    assert execution.state is ExecutionState.COMPLETED
    assert (await engine.audit(execution.id))[1].valid


async def test_failed_rollback_leaves_the_step_failed(tmp_path: Path) -> None:
    executor = _fake()
    executor.script("drsim", "k8s_rollout_restart", ToolError("connection refused"))
    executor.script("drsim", "k8s_rollout_undo", ToolResult(ok=False, content=""))
    engine, execution = await _started(tmp_path, executor)
    execution = await engine.advance(execution.id)
    assert execution.step(2).summary == "connection refused"
    rollback = execution.step(2).rollback
    assert rollback is not None
    await engine.decide(execution.id, 2, Approve("Ann", rollback.call_hash, kind=CallKind.ROLLBACK))
    execution = await engine.rollback(execution.id, 2, OPERATOR)
    step = execution.step(2)
    assert step.state is StepState.FAILED
    assert step.summary == "rollback failed: the tool reported failure"


async def test_retry_needs_fresh_approval(tmp_path: Path) -> None:
    executor = _fake()
    executor.script("drsim", "k8s_rollout_restart", ToolResult(ok=False, content="flaky"))
    engine, execution = await _started(tmp_path, executor)
    execution = await engine.advance(execution.id)
    execution = await engine.decide(execution.id, 2, Retry("Ann"))
    step = execution.step(2)
    assert (step.state, step.attempt) == (StepState.AWAITING_APPROVAL, 2)
    assert step.call is not None
    assert step.call.approvals == []
    assert step.call.result is None
    await engine.decide(execution.id, 2, Approve("Ben", step.call.call_hash))
    await engine.resume(execution.id, OPERATOR)
    execution = await engine.advance(execution.id)
    assert execution.step(2).state is StepState.SUCCEEDED


async def test_verify_failure_fails_the_step(tmp_path: Path) -> None:
    executor = _fake()
    # k8s_rollout_status is step 1's main call, then step 2's verify call.
    executor.script(
        "drsim",
        "k8s_rollout_status",
        ToolResult(ok=True, content="primary down"),
        ToolResult(ok=False, content="0/3 ready"),
    )
    engine, execution = await _started(tmp_path, executor)
    execution = await engine.advance(execution.id)
    step = execution.step(2)
    assert (step.state, step.summary) == (StepState.FAILED, "0/3 ready")
    assert step.call is not None
    assert step.call.result is not None
    assert step.call.result.ok
    assert execution.state is ExecutionState.PAUSED


@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        (RuntimeError("boom"), "executor error: RuntimeError"),
        (ToolError("x" * 600), "x" * 500),
    ],
)
async def test_executor_errors_fail_the_step(
    tmp_path: Path, outcome: Exception, error: str
) -> None:
    executor = _fake()
    executor.script("drsim", "k8s_rollout_status", outcome)
    engine, execution = await _started(tmp_path, executor)
    execution = await engine.advance(execution.id)
    step = execution.step(1)
    assert step.state is StepState.FAILED
    assert step.call is not None
    assert step.call.error == error


async def test_call_timeout_fails_the_step(tmp_path: Path) -> None:
    executor = FakeExecutor(drsim_catalog(), gate=asyncio.Event())  # never released
    engine, execution = await _started(tmp_path, executor, tool_timeout_seconds=0.01)
    execution = await engine.advance(execution.id)
    assert execution.step(1).state is StepState.FAILED
    assert execution.step(1).summary == "timed out after 0.01 s"


async def test_tool_call_limit_pauses_the_execution(tmp_path: Path) -> None:
    executor = _fake()
    executor.script("drsim", "k8s_rollout_restart", ToolResult(ok=False, content="no"))
    engine, execution = await _started(tmp_path, executor, max_tool_calls=2)
    execution = await engine.advance(execution.id)
    assert execution.tool_calls_used == 2
    rollback = execution.step(2).rollback
    assert rollback is not None
    await engine.decide(execution.id, 2, Approve("Ann", rollback.call_hash, kind=CallKind.ROLLBACK))
    with pytest.raises(PolicyViolationError, match="tool call limit"):
        await engine.rollback(execution.id, 2, OPERATOR)
    await engine.decide(execution.id, 2, Skip("Ann", "fix by hand"))
    await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "ok"))
    await engine.resume(execution.id, OPERATOR)
    execution = await engine.advance(execution.id)
    assert execution.pause_reason == "tool call limit reached"
    assert execution.step(3).state is StepState.APPROVED


async def test_calls_are_rechecked_against_policy_right_before_running(tmp_path: Path) -> None:
    engine, execution = await _started(tmp_path, _fake())
    stricter = json.loads(json.dumps(drsim_policy_dict()))
    del stricter["servers"]["drsim"]["tools"]["k8s_rollout_restart"]
    engine2, _, _ = await make_engine(tmp_path, _fake(), policy=parse_policy(json.dumps(stricter)))
    execution = await engine2.advance(execution.id)
    step = execution.step(2)
    assert step.state is StepState.AWAITING_APPROVAL
    assert step.summary == "approval no longer valid; approve again"
    assert step.policy_errors
    assert step.call is not None
    assert step.call.approvals == []
    assert engine is not engine2
