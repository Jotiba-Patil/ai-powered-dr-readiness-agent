"""Abort during a call, and restart recovery: in-flight calls become UNKNOWN, nothing resumes."""

import asyncio
from pathlib import Path

import pytest
from exec_support import (
    OPERATOR,
    approve_waiting,
    drsim_catalog,
    executable_runbook,
    make_engine,
)

from dr_agent.execution.decisions import Approve, ReportOutcome
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.journal import Journal
from dr_agent.execution.models import (
    CallKind,
    Execution,
    ExecutionMode,
    ExecutionState,
    StepState,
)
from dr_agent.execution.recovery import recover_interrupted
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.execution.transitions import ExecutionEvent
from dr_agent.tools.base import ToolResult
from dr_agent.tools.fake import FakeExecutor
from dr_agent.utils.errors import ConflictError, InvalidTransitionError


async def _running_with_call_in_flight(
    tmp_path: Path,
) -> tuple[ExecutionEngine, SqliteExecutionStore, FakeExecutor, Execution, asyncio.Task[Execution]]:
    executor = FakeExecutor(drsim_catalog(), gate=asyncio.Event())
    engine, store, _ = await make_engine(tmp_path, executor)
    execution = await engine.create(
        executable_runbook(), mode=ExecutionMode.LIVE, started_by=OPERATOR, runbook_label="s"
    )
    execution = await approve_waiting(engine, execution)
    await engine.start(execution.id, OPERATOR)
    task = asyncio.create_task(engine.advance(execution.id))
    await executor.started.wait()
    return engine, store, executor, execution, task


async def test_abort_mid_call_marks_the_step_unknown(tmp_path: Path) -> None:
    engine, _, executor, execution, task = await _running_with_call_in_flight(tmp_path)
    assert (await engine.get(execution.id)).step(1).state is StepState.RUNNING
    aborted = await engine.abort(execution.id, OPERATOR, "wrong region")
    assert aborted.state is ExecutionState.ABORTED
    assert aborted.step(1).state is StepState.UNKNOWN
    assert executor.gate is not None
    executor.gate.set()
    final = await task
    assert final.step(1).state is StepState.UNKNOWN  # the late result changes nothing
    assert len(executor.calls) == 1
    events, chain = await engine.audit(execution.id)
    assert chain.valid
    assert events[-1].type == "tool_result"
    assert events[-1].payload["late"] is True
    with pytest.raises(InvalidTransitionError):
        await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "checked"))


async def test_restart_turns_running_steps_unknown_and_pauses(tmp_path: Path) -> None:
    engine, store, executor, execution, task = await _running_with_call_in_flight(tmp_path)
    recovered = await recover_interrupted(store, lambda: execution.created_at)
    assert recovered == [execution.id]
    after = await store.get(execution.id)
    assert after.step(1).state is StepState.UNKNOWN
    assert after.state is ExecutionState.PAUSED
    assert after.pause_reason == "the service restarted; resume when ready"
    events = await store.audit(execution.id)
    assert any(e.type == "recovery" and e.payload == {"unknownSteps": [1]} for e in events)

    assert executor.gate is not None
    executor.gate.set()
    await task  # the old process's result arrives late and is only recorded
    await engine.decide(execution.id, 1, ReportOutcome("Ann", True, "status page checked"))
    assert (await engine.get(execution.id)).step(1).state is StepState.SUCCEEDED
    assert await recover_interrupted(store, lambda: execution.created_at) == []


async def test_restart_recovers_verify_and_rollback_calls(tmp_path: Path) -> None:
    engine, store, _ = await make_engine(tmp_path)
    execution = await engine.create(
        executable_runbook(), mode=ExecutionMode.LIVE, started_by=OPERATOR, runbook_label="s"
    )
    now = execution.created_at
    # Simulate a crash in the middle of step 2's verify call and step 4's rollback call.
    step2, step4 = execution.step(2), execution.step(4)
    assert step2.verify is not None
    step2.state, step2.verify.started_at = StepState.VERIFYING, now
    step4.state = StepState.FAILED
    step4.rollback = step2.rollback.model_copy() if step2.rollback else None
    assert step4.rollback is not None
    step4.rollback.started_at = now
    journal = Journal(execution, now)
    journal.move_execution(ExecutionEvent.START, OPERATOR)
    await store.save(execution, journal.events)

    await recover_interrupted(store, lambda: now)
    after = await store.get(execution.id)
    assert after.step(2).state is StepState.UNKNOWN
    assert after.step(4).state is StepState.FAILED
    assert after.step(4).rollback is not None
    assert after.step(4).rollback.error == "the service restarted; outcome unknown"
    assert after.step(4).summary == "rollback outcome unknown; check the system"
    assert after.state is ExecutionState.PAUSED
    assert (await engine.audit(execution.id))[1].valid


async def test_idle_and_terminal_executions(tmp_path: Path) -> None:
    engine, store, _ = await make_engine(tmp_path)
    idle = await engine.create(
        executable_runbook(), mode=ExecutionMode.DRY_RUN, started_by=OPERATOR, runbook_label="s"
    )
    created = await engine.create(
        executable_runbook(), mode=ExecutionMode.DRY_RUN, started_by=OPERATOR, runbook_label="s"
    )
    done = await engine.create(
        executable_runbook(), mode=ExecutionMode.DRY_RUN, started_by=OPERATOR, runbook_label="s"
    )
    await engine.start(idle.id, OPERATOR)
    await engine.abort(done.id, OPERATOR, "not needed")
    assert await recover_interrupted(store, lambda: idle.created_at) == [idle.id]
    assert (await store.get(idle.id)).state is ExecutionState.PAUSED
    assert (await store.get(created.id)).state is ExecutionState.CREATED
    assert (await store.get(done.id)).state is ExecutionState.ABORTED


async def test_rollback_is_refused_while_another_call_runs(tmp_path: Path) -> None:
    engine, _, executor, execution, task = await _running_with_call_in_flight(tmp_path)
    with pytest.raises(ConflictError, match="already in progress"):
        await engine.rollback(execution.id, 2, OPERATOR)
    assert executor.gate is not None
    executor.gate.set()
    await task


async def test_abort_during_a_rollback_call(tmp_path: Path) -> None:
    executor = FakeExecutor(drsim_catalog())
    executor.script("drsim", "k8s_rollout_restart", ToolResult(ok=False, content="crashloop"))
    engine, _, _ = await make_engine(tmp_path, executor)
    execution = await engine.create(
        executable_runbook(), mode=ExecutionMode.LIVE, started_by=OPERATOR, runbook_label="s"
    )
    execution = await approve_waiting(engine, execution)
    await engine.start(execution.id, OPERATOR)
    execution = await engine.advance(execution.id)
    rollback = execution.step(2).rollback
    assert rollback is not None
    await engine.decide(execution.id, 2, Approve("Ann", rollback.call_hash, kind=CallKind.ROLLBACK))

    executor.gate = asyncio.Event()
    executor.started.clear()
    task = asyncio.create_task(engine.rollback(execution.id, 2, OPERATOR))
    await executor.started.wait()
    await engine.abort(execution.id, OPERATOR, "stop everything")
    executor.gate.set()
    final = await task
    step = final.step(2)
    assert step.state is StepState.FAILED
    assert step.summary == "rollback outcome unknown; check the system"
    events, chain = await engine.audit(execution.id)
    assert chain.valid
    assert events[-1].payload["late"] is True
    with pytest.raises(InvalidTransitionError, match="execution is ABORTED"):
        await engine.rollback(execution.id, 2, OPERATOR)
