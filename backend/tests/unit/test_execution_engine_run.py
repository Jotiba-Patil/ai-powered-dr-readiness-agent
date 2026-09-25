"""Engine happy paths: switches, dry run and live run of the executable sample."""

from pathlib import Path

import pytest
from exec_support import (
    OPERATOR,
    approve_waiting,
    drsim_catalog,
    executable_runbook,
    make_engine,
)

from dr_agent.execution.decisions import ReportOutcome
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import Execution, ExecutionMode, ExecutionState, StepState
from dr_agent.tools.dry_run import DryRunExecutor
from dr_agent.tools.fake import FakeExecutor
from dr_agent.utils.errors import CapacityError, ExecutionDisabledError, InvalidTransitionError


async def _create(
    engine: ExecutionEngine, mode: ExecutionMode = ExecutionMode.DRY_RUN
) -> Execution:
    return await engine.create(
        executable_runbook(), mode=mode, started_by=OPERATOR, runbook_label="sample.md"
    )


async def _drive_to_completion(engine: ExecutionEngine, execution: Execution) -> Execution:
    """Approve everything, start, and confirm step 1 (it has no verify tool)."""
    execution = await approve_waiting(engine, execution)
    await engine.start(execution.id, OPERATOR)
    execution = await engine.advance(execution.id)
    assert execution.step(1).state is StepState.VERIFYING
    assert execution.step(3).state is StepState.APPROVED  # waits for step 1
    await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "dashboard shows outage"))
    return await engine.advance(execution.id)


async def test_everything_is_refused_while_disabled(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path, enabled=False)
    with pytest.raises(ExecutionDisabledError) as info:
        await _create(engine)
    assert info.value.code == "EXECUTION_DISABLED"
    for call in (engine.get("x"), engine.list_all(), engine.advance("x"), engine.audit("x")):
        with pytest.raises(ExecutionDisabledError):
            await call


async def test_live_runs_need_the_second_switch(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path, allow_live=False)
    with pytest.raises(ExecutionDisabledError, match="EXECUTION_ALLOW_LIVE"):
        await _create(engine, ExecutionMode.LIVE)
    assert (await _create(engine)).mode is ExecutionMode.DRY_RUN


async def test_dry_run_end_to_end(tmp_path: Path) -> None:
    executor = DryRunExecutor(drsim_catalog())
    engine, _, _ = await make_engine(tmp_path, executor)
    execution = await _drive_to_completion(engine, await _create(engine))

    assert execution.state is ExecutionState.COMPLETED
    assert all(run.state is StepState.SUCCEEDED for run in execution.steps)
    assert execution.tool_calls_used == 9  # 5 main + 4 verify calls
    assert [tool for _, tool, _ in executor.calls] == [
        "k8s_rollout_status",
        "k8s_rollout_restart",
        "k8s_rollout_status",
        "db_promote_replica",
        "db_is_in_recovery",
        "cache_warm_from_snapshot",
        "cache_ping",
        "dns_switch_region",
        "smoke_run",
    ]
    call = execution.step(5).call
    assert call is not None
    assert call.result is not None
    assert call.result.simulated
    events, chain = await engine.audit(execution.id)
    assert chain.valid
    assert chain.head == execution.audit_head == events[-1].hash
    assert events[-1].payload["to"] == "COMPLETED"


async def test_live_run_uses_the_injected_executor(tmp_path: Path) -> None:
    executor = FakeExecutor(drsim_catalog())
    engine, _, _ = await make_engine(tmp_path, executor)
    execution = await _drive_to_completion(engine, await _create(engine, ExecutionMode.LIVE))
    assert execution.state is ExecutionState.COMPLETED
    assert len(executor.calls) == 9
    assert (await engine.list_all())[0].id == execution.id


async def test_nothing_runs_before_start_or_without_approval(tmp_path: Path) -> None:
    executor = FakeExecutor(drsim_catalog())
    engine, _, _ = await make_engine(tmp_path, executor)
    execution = await _create(engine)
    assert (await engine.advance(execution.id)).state is ExecutionState.CREATED
    await engine.start(execution.id, OPERATOR)
    execution = await engine.advance(execution.id)
    assert executor.calls == []
    assert {run.state for run in execution.steps} == {StepState.AWAITING_APPROVAL}
    assert execution.state is ExecutionState.RUNNING


async def test_active_execution_cap(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path, max_active=1)
    first, second = await _create(engine), await _create(engine)
    await engine.start(first.id, OPERATOR)
    with pytest.raises(CapacityError):
        await engine.start(second.id, OPERATOR)
    await engine.abort(first.id, OPERATOR, "drill over")
    assert (await engine.start(second.id, OPERATOR)).state is ExecutionState.RUNNING


async def test_lifecycle_transitions_are_checked(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path)
    execution = await _create(engine)
    with pytest.raises(InvalidTransitionError):
        await engine.resume(execution.id, OPERATOR)
    await engine.start(execution.id, OPERATOR)
    paused = await engine.pause(execution.id, OPERATOR, "coffee")
    assert (paused.state, paused.pause_reason) == (ExecutionState.PAUSED, "coffee")
    resumed = await engine.resume(execution.id, OPERATOR)
    assert (resumed.state, resumed.pause_reason) == (ExecutionState.RUNNING, None)
    closed = await engine.close(execution.id, OPERATOR, "unrecoverable")
    assert closed.state is ExecutionState.FAILED
    with pytest.raises(InvalidTransitionError, match="execution is FAILED"):
        await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "x"))
    with pytest.raises(InvalidTransitionError):
        await engine.abort(execution.id, OPERATOR, "too late")
