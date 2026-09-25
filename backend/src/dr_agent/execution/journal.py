"""Applies state changes to an in-memory `Execution` and records their audit events.

A `Journal` covers one unit of work: the store saves the changed execution and
`journal.events` in one transaction, so a state change and its audit event can
never diverge (ADR 0004). All transitions go through the tables in
`transitions.py`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import JsonValue

from dr_agent.execution.audit import AuditEvent, build_event, genesis_hash
from dr_agent.execution.models import Execution, ExecutionState, StepRun, StepState
from dr_agent.execution.transitions import (
    WAITING_STEP_STATES,
    ExecutionEvent,
    StepEvent,
    next_execution_state,
    next_step_state,
)

SYSTEM_ACTOR = "system"


class AuditType(StrEnum):
    EXECUTION_CREATED = "execution_created"
    EXECUTION_STATE = "execution_state"
    STEP_STATE = "step_state"
    CALL_SET = "call_set"
    APPROVAL = "approval"
    PROPOSAL = "proposal"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RECOVERY = "recovery"


class Journal:
    def __init__(self, execution: Execution, now: datetime) -> None:
        self.execution = execution
        self.now = now
        self.events: list[AuditEvent] = []

    def record(
        self, event_type: AuditType, actor: str, payload: dict[str, JsonValue] | None = None
    ) -> AuditEvent:
        execution = self.execution
        event = build_event(
            execution_id=execution.id,
            seq=execution.audit_seq + 1,
            prev_hash=execution.audit_head or genesis_hash(execution.id),
            event_type=event_type.value,
            actor=actor,
            payload=payload or {},
            now=self.now,
        )
        execution.audit_seq, execution.audit_head = event.seq, event.hash
        execution.updated_at = self.now
        self.events.append(event)
        return event

    def move_step(
        self, run: StepRun, event: StepEvent, actor: str, reason: str | None = None
    ) -> None:
        old = run.state
        run.state = next_step_state(old, event)
        waiting = run.state in WAITING_STEP_STATES or (
            run.state is StepState.VERIFYING and run.verify is None
        )
        run.waiting_since = self.now if waiting else None
        if reason:
            run.summary = reason
        payload: dict[str, JsonValue] = {
            "step": run.step_number,
            "from": old.value,
            "to": run.state.value,
            "event": event.value,
        }
        if reason:
            payload["reason"] = reason
        self.record(AuditType.STEP_STATE, actor, payload)

    def move_execution(self, event: ExecutionEvent, actor: str, reason: str | None = None) -> None:
        execution = self.execution
        old = execution.state
        execution.state = next_execution_state(old, event)
        execution.pause_reason = reason if execution.state is ExecutionState.PAUSED else None
        payload: dict[str, JsonValue] = {
            "from": old.value,
            "to": execution.state.value,
            "event": event.value,
        }
        if reason:
            payload["reason"] = reason
        self.record(AuditType.EXECUTION_STATE, actor, payload)

    def restart_waiting_clocks(self) -> None:
        """Waiting time only counts while the execution runs (start and resume reset it)."""
        for run in self.execution.steps:
            if run.waiting_since is not None:
                run.waiting_since = self.now
