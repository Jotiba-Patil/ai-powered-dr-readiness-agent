"""SQL for the execution store (ADR 0004) and the row projections of one execution.

The tables themselves are created by `storage/migrations.py`.

`executions.plan_json` holds the full execution document and is what the store
loads. `step_runs`, `tool_calls` and `approvals` are written in the same
transaction as queryable projections of it; `audit_events` is append-only.
"""

from __future__ import annotations

from dr_agent.execution.audit import AuditEvent
from dr_agent.execution.canonical import canonical_json
from dr_agent.execution.models import Execution, ToolCall

# An upsert, not INSERT OR REPLACE: REPLACE deletes the row first, and the
# ON DELETE CASCADE would then wipe the execution's audit events.
# `analysis_id` is set only when that analysis is stored (history may be off,
# or the CLI ran with --no-save), and never changed afterwards.
INSERT_EXECUTION = (
    "INSERT INTO executions (id, state, mode, runbook_label, runbook_sha256, started_by, "
    "created_at, updated_at, audit_seq, audit_head, plan_json, analysis_id) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,(SELECT id FROM analyses WHERE id = ?)) "
    "ON CONFLICT(id) DO UPDATE SET "
    "state = excluded.state, updated_at = excluded.updated_at, "
    "audit_seq = excluded.audit_seq, audit_head = excluded.audit_head, "
    "plan_json = excluded.plan_json"
)
INSERT_STEP = "INSERT INTO step_runs VALUES (?,?,?,?,?,?)"
INSERT_CALL = "INSERT INTO tool_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
INSERT_APPROVAL = "INSERT INTO approvals VALUES (?,?,?,?,?,?,?)"
INSERT_EVENT = "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)"
DELETE_PROJECTIONS = (
    "DELETE FROM step_runs WHERE execution_id = ?",
    "DELETE FROM tool_calls WHERE execution_id = ?",
    "DELETE FROM approvals WHERE execution_id = ?",
)
SELECT_EVENTS = (
    "SELECT seq, execution_id, type, actor, payload_json, prev_hash, hash, created_at "
    "FROM audit_events WHERE execution_id = ? ORDER BY seq"
)
EVENT_COLUMNS = ("seq", "executionId", "type", "actor", "payload", "prevHash", "hash", "createdAt")

Row = tuple[str | int | None, ...]


def execution_row(execution: Execution) -> Row:
    return (
        execution.id,
        execution.state.value,
        execution.mode.value,
        execution.runbook_label,
        execution.runbook_sha256,
        execution.started_by,
        execution.created_at.isoformat(),
        execution.updated_at.isoformat(),
        execution.audit_seq,
        execution.audit_head,
        execution.model_dump_json(by_alias=True),
        execution.analysis.job_id if execution.analysis else None,
    )


def event_row(event: AuditEvent) -> Row:
    return (
        event.execution_id,
        event.seq,
        event.type,
        event.actor,
        canonical_json(event.payload),
        event.prev_hash,
        event.hash,
        event.created_at.isoformat(),
    )


def projections(execution: Execution) -> tuple[list[Row], list[Row], list[Row]]:
    steps: list[Row] = []
    calls: list[Row] = []
    approvals: list[Row] = []
    for run in execution.steps:
        steps.append(
            (execution.id, run.step_number, run.phase, run.state.value, run.attempt, run.summary)
        )
        for call in (run.call, run.verify, run.rollback):
            if call is None:
                continue
            calls.append((execution.id, run.step_number, *_call_columns(call)))
            approvals.extend(
                (
                    execution.id,
                    run.step_number,
                    call.kind.value,
                    a.approver,
                    a.comment,
                    a.call_hash,
                    a.created_at.isoformat(),
                )
                for a in call.approvals
            )
    return steps, calls, approvals


def _call_columns(call: ToolCall) -> Row:
    return (
        call.kind.value,
        call.server,
        call.tool,
        canonical_json(call.arguments),
        call.source.value,
        call.risk_class.value if call.risk_class else None,
        call.call_hash,
        call.result.model_dump_json(by_alias=True) if call.result else None,
        call.error,
        call.started_at.isoformat() if call.started_at else None,
        call.finished_at.isoformat() if call.finished_at else None,
    )
