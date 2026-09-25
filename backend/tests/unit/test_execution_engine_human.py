"""Human decisions through the engine: manual steps, review, edits, approvals, timeouts."""

from pathlib import Path

import pytest
from exec_support import OPERATOR, Clock, approve_waiting, executable_runbook, make_engine

from dr_agent.core.parser import parse_runbook
from dr_agent.execution.decisions import (
    Approve,
    ConvertToManual,
    EditCall,
    MarkDone,
    Reject,
    ReportOutcome,
    Skip,
)
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import (
    CallKind,
    CallSource,
    Execution,
    ExecutionMode,
    ExecutionState,
    StepState,
)
from dr_agent.models.runbook import PlannedToolCall
from dr_agent.utils.errors import (
    InvalidTransitionError,
    NotFoundError,
    PolicyViolationError,
    StaleCallError,
    ValidationError,
)

MIXED = (
    "# Svc\n\n**Owner:** Ann\n**RTO:** 30 min\n**RPO:** 5 min\n\n## Recovery Steps\n\n"
    "1. Page the DBA. Owner: Ann. 5 min.\n"
    "2. Ping the cache (after step 1). Owner: Ann. 5 min.\n"
    '   - Tool: `drsim/cache_ping {"cache": "pricing-cache"}`\n'
    "3. Wipe it. Owner: Ann. 5 min.\n"
    "   - Tool: `drsim/drop_database {}`\n"
)
PING = PlannedToolCall(server="drsim", tool="cache_ping", arguments={"cache": "c"})


async def _create(engine: ExecutionEngine, markdown: str | None = None) -> Execution:
    runbook = parse_runbook(markdown) if markdown else executable_runbook()
    return await engine.create(
        runbook, mode=ExecutionMode.LIVE, started_by=OPERATOR, runbook_label="t"
    )


async def test_manual_and_proposed_steps(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path)
    execution = await _create(engine, MIXED)
    assert [run.step_number for run in execution.steps] == [1, 3, 2]  # phase order
    states = {run.step_number: run.state for run in execution.steps}
    assert states == {
        1: StepState.AWAITING_MANUAL,
        2: StepState.AWAITING_APPROVAL,
        3: StepState.PROPOSED,
    }

    with pytest.raises(PolicyViolationError, match="not allow-listed"):
        await engine.decide(execution.id, 3, EditCall("Ann"))  # accept as-is
    execution = await engine.decide(execution.id, 3, EditCall("Ann", PING))
    step3 = execution.step(3)
    assert step3.state is StepState.AWAITING_APPROVAL
    assert step3.call is not None
    assert step3.call.source is CallSource.EDITED
    assert step3.policy_errors == []
    execution = await engine.decide(execution.id, 3, Reject("Ben", "wrong cache"))
    assert execution.step(3).state is StepState.REJECTED
    execution = await engine.decide(execution.id, 3, ConvertToManual("Ben", "do it by hand"))
    assert execution.step(3).state is StepState.AWAITING_MANUAL

    execution = await approve_waiting(engine, execution)
    await engine.start(execution.id, OPERATOR)
    execution = await engine.advance(execution.id)
    assert execution.step(2).state is StepState.APPROVED  # blocked by manual step 1
    await engine.decide(execution.id, 1, MarkDone("Ann", "DBA paged"))
    await engine.decide(execution.id, 3, MarkDone("Ann"))
    execution = await engine.advance(execution.id)
    assert execution.step(2).state is StepState.VERIFYING
    await engine.decide(execution.id, 2, ReportOutcome("Ann", False, "cache still cold"))
    execution = await engine.get(execution.id)
    assert execution.step(2).state is StepState.FAILED


async def test_approval_rules_through_the_engine(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path)
    execution = await _create(engine)
    step3 = execution.step(3)
    assert step3.call is not None
    with pytest.raises(StaleCallError):
        await engine.decide(execution.id, 3, Approve("Ann", "0" * 64))
    with pytest.raises(PolicyViolationError, match="started the execution"):
        await engine.decide(execution.id, 3, Approve(OPERATOR, step3.call.call_hash))
    execution = await engine.decide(execution.id, 3, Approve("Ann", step3.call.call_hash))
    assert execution.step(3).state is StepState.AWAITING_APPROVAL  # destructive: 1 of 2
    execution = await engine.decide(execution.id, 3, Approve("Ben", step3.call.call_hash))
    assert execution.step(3).state is StepState.APPROVED
    with pytest.raises(InvalidTransitionError, match="not awaiting approval"):
        await engine.decide(execution.id, 3, Approve("Cid", step3.call.call_hash))
    with pytest.raises(InvalidTransitionError, match="only be approved for a failed step"):
        await engine.decide(execution.id, 3, Approve("Cid", "x", kind=CallKind.ROLLBACK))
    with pytest.raises(InvalidTransitionError, match="no verify call"):
        await engine.decide(execution.id, 2, Approve("Cid", "x", kind=CallKind.VERIFY))
    with pytest.raises(NotFoundError):
        await engine.decide(execution.id, 42, Skip("Ann", "no such step"))
    with pytest.raises(ValidationError):
        await engine.decide(execution.id, 3, Skip("Ann", "  "))


async def test_editing_clears_approvals(tmp_path: Path) -> None:
    engine, _, _ = await make_engine(tmp_path)
    execution = await approve_waiting(engine, await _create(engine))
    assert execution.step(2).state is StepState.APPROVED

    restart = PlannedToolCall(
        server="drsim",
        tool="k8s_rollout_restart",
        arguments={"deployment": "estimate-service", "region": "primary"},
    )
    execution = await engine.decide(execution.id, 2, EditCall("Ann", restart))
    step2 = execution.step(2)
    assert step2.state is StepState.AWAITING_APPROVAL
    assert step2.call is not None
    assert step2.call.approvals == []

    execution = await engine.decide(execution.id, 2, EditCall("Ann", None, CallKind.VERIFY))
    assert execution.step(2).verify is None
    warm = PlannedToolCall(
        server="drsim", tool="cache_warm_from_snapshot", arguments={"cache": "c", "snapshot": "s"}
    )
    with pytest.raises(PolicyViolationError, match="read-only"):
        await engine.decide(execution.id, 2, EditCall("Ann", warm, CallKind.VERIFY))

    undo = PlannedToolCall(
        server="drsim",
        tool="k8s_rollout_undo",
        arguments={"deployment": "estimate-service", "region": "primary"},
    )
    execution = await engine.decide(execution.id, 2, EditCall("Ann", undo, CallKind.ROLLBACK))
    step2 = execution.step(2)
    assert step2.rollback is not None
    assert step2.rollback.arguments["region"] == "primary"
    assert step2.state is StepState.AWAITING_APPROVAL
    with pytest.raises(ValidationError, match="rollback call is required"):
        await engine.decide(execution.id, 2, EditCall("Ann", None, CallKind.ROLLBACK))
    await engine.decide(execution.id, 1, Skip("Ann", "not needed"))
    with pytest.raises(InvalidTransitionError, match="already finished"):
        await engine.decide(execution.id, 1, EditCall("Ann", undo, CallKind.ROLLBACK))


async def test_waiting_too_long_pauses_the_execution(tmp_path: Path) -> None:
    clock = Clock()
    engine, _, _ = await make_engine(tmp_path, clock=clock)
    execution = await _create(engine)
    clock.advance(120)  # time before start does not count
    await engine.start(execution.id, OPERATOR)
    clock.advance(30)
    assert (await engine.advance(execution.id)).state is ExecutionState.RUNNING
    clock.advance(1)
    execution = await engine.advance(execution.id)
    assert execution.state is ExecutionState.PAUSED
    assert execution.pause_reason == "step 1 waited more than 30 minutes for a person"
    await engine.resume(execution.id, OPERATOR)
    assert (await engine.advance(execution.id)).state is ExecutionState.RUNNING
