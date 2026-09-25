"""Helpers for the knowledge-base tests: finished executions with hand-made audit trails."""

from __future__ import annotations

from datetime import timedelta

from exec_support import OPERATOR, drsim_catalog, drsim_policy, executable_runbook
from history_support import T0

from dr_agent.execution.audit import AuditEvent
from dr_agent.execution.models import ExecutionMode, ExecutionState, StepState
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.knowledge.facts import PastRun


def event(execution_id: str, seq: int, minute: float, kind: str, **payload: object) -> AuditEvent:
    return AuditEvent.model_validate(
        {
            "seq": seq,
            "executionId": execution_id,
            "type": kind,
            "actor": "system",
            "payload": payload,
            "prevHash": "0" * 64,
            "hash": "1" * 64,
            "createdAt": T0 + timedelta(minutes=minute),
        }
    )


def finished_run(
    execution_id: str,
    *,
    step_minutes: dict[int, tuple[float, float]],
    end_states: dict[int, StepState] | None = None,
    total: float = 60.0,
    state: ExecutionState = ExecutionState.COMPLETED,
    rto: float = 60.0,
    attempts: dict[int, int] | None = None,
) -> PastRun:
    """A live run of the executable sample: step n runs from minute a to b (after approval at 0)."""
    execution, _ = plan_execution(
        executable_runbook(),
        policy=drsim_policy(),
        catalog=index_catalog(drsim_catalog()),
        execution_id=execution_id,
        mode=ExecutionMode.LIVE,
        started_by=OPERATOR,
        runbook_label="estimate-service-executable.md",
        now=T0,
    )
    execution.state = state
    ends = end_states or {}
    for run in execution.steps:
        run.state = ends.get(run.step_number, StepState.SUCCEEDED)
        run.attempt = (attempts or {}).get(run.step_number, 1)
    events = [event(execution_id, 1, 0, "execution_state", to="RUNNING")]
    for number, (start, end) in step_minutes.items():
        final = ends.get(number, StepState.SUCCEEDED).value
        for minute, to in ((-5, "AWAITING_APPROVAL"), (start, "RUNNING"), (end, final)):
            events.append(
                event(execution_id, len(events) + 1, minute, "step_state", step=number, to=to)
            )
    events.append(event(execution_id, len(events) + 1, total, "execution_state", to=state.value))
    return PastRun(execution=execution, events=events, stated_rto_minutes=rto)
