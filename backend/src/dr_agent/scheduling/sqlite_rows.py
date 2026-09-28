"""SQL and row mapping for the SQLite `ScheduleStore` (migration 3).

Column lists are module constants and every value is a `?` parameter, so the
f-strings below never contain input (hence the file-wide S608 exemption).
"""

# ruff: noqa: S608

from __future__ import annotations

import json
from datetime import datetime

from pydantic import TypeAdapter

from dr_agent.scheduling.models import Cadence, Schedule, SchedulerState, ScheduleRun
from dr_agent.storage.sqlite import timestamp

Row = tuple[object, ...]

SCHEDULE_COLUMNS = (
    "id, name, runbook_path, inventory_path, cadence_json, timezone, recipients_json, "
    "enabled, pause_until, paused_by, paused_at, created_by, created_at, updated_at, "
    "next_run_at, last_run_at"
)
RUN_COLUMNS = (
    "id, schedule_id, slot_at, trigger, state, started_at, finished_at, job_id, analysis_id, "
    "risk_score, risk_level, rto_feasible, email_state, email_to, error_code, error"
)
INSERT_SCHEDULE = f"INSERT INTO schedules ({SCHEDULE_COLUMNS}) VALUES ({', '.join('?' * 16)})"
UPDATE_SCHEDULE = (
    "UPDATE schedules SET name = ?, runbook_path = ?, inventory_path = ?, cadence_json = ?, "
    "timezone = ?, recipients_json = ?, enabled = ?, pause_until = ?, paused_by = ?, "
    "paused_at = ?, created_by = ?, created_at = ?, updated_at = ?, next_run_at = ?, "
    "last_run_at = ? WHERE id = ?"
)
SELECT_SCHEDULE = f"SELECT {SCHEDULE_COLUMNS} FROM schedules WHERE id = ?"
SELECT_SCHEDULES = f"SELECT {SCHEDULE_COLUMNS} FROM schedules ORDER BY created_at, id"
SELECT_DUE = (
    f"SELECT {SCHEDULE_COLUMNS} FROM schedules WHERE enabled = 1 AND next_run_at <= ? "
    "ORDER BY next_run_at, id"
)
SELECT_EXPIRED_PAUSES = (
    f"SELECT {SCHEDULE_COLUMNS} FROM schedules "
    "WHERE enabled = 0 AND pause_until IS NOT NULL AND pause_until <= ?"
)
SELECT_ACTIVE = f"SELECT {SCHEDULE_COLUMNS} FROM schedules WHERE enabled = 1"
SET_NEXT_RUN = (
    "UPDATE schedules SET next_run_at = ?, last_run_at = COALESCE(?, last_run_at) WHERE id = ?"
)
DELETE_SCHEDULE = "DELETE FROM schedules WHERE id = ?"
RUNNING_OF = "SELECT 1 FROM schedule_runs WHERE schedule_id = ? AND state = 'running' LIMIT 1"
INSERT_RUN = f"INSERT INTO schedule_runs ({RUN_COLUMNS}) VALUES ({', '.join('?' * 16)})"
UPDATE_RUN = f"REPLACE INTO schedule_runs ({RUN_COLUMNS}) VALUES ({', '.join('?' * 16)})"
SELECT_RUN = f"SELECT {RUN_COLUMNS} FROM schedule_runs WHERE id = ?"
SELECT_LATEST_RUNS = (
    f"SELECT {RUN_COLUMNS} FROM schedule_runs r WHERE started_at = "
    "(SELECT MAX(started_at) FROM schedule_runs WHERE schedule_id = r.schedule_id)"
)
FAIL_INTERRUPTED = (
    "UPDATE schedule_runs SET state = 'failed', finished_at = ?, error_code = 'INTERRUPTED', "
    "error = 'the server stopped while this run was going' WHERE state = 'running'"
)
SELECT_STATE = "SELECT paused, pause_until, paused_by, paused_at FROM scheduler_state WHERE id = 1"
UPDATE_STATE = (
    "UPDATE scheduler_state SET paused = ?, pause_until = ?, paused_by = ?, paused_at = ? "
    "WHERE id = 1"
)

_CADENCE: TypeAdapter[Cadence] = TypeAdapter(Cadence)


def runs_page_sql(before: datetime | None) -> str:
    where = "schedule_id = ?" + (" AND started_at < ?" if before else "")
    return f"SELECT {RUN_COLUMNS} FROM schedule_runs WHERE {where} ORDER BY started_at DESC LIMIT ?"


def ts(value: datetime | None) -> str | None:
    return timestamp(value) if value else None


def schedule_row(s: Schedule) -> Row:
    cadence = json.dumps(_CADENCE.dump_python(s.cadence, mode="json", by_alias=True))
    recipients = json.dumps(s.recipients) if s.recipients else None
    return (
        s.id, s.name, s.runbook_path, s.inventory_path, cadence, s.timezone, recipients,
        int(s.enabled), ts(s.pause_until), s.paused_by, ts(s.paused_at), s.created_by,
        ts(s.created_at), ts(s.updated_at), ts(s.next_run_at), ts(s.last_run_at),
    )  # fmt: skip


def schedule_from_row(row: Row) -> Schedule:
    fields = SCHEDULE_COLUMNS.split(", ")
    data = dict(zip(fields, row, strict=True))
    data["cadence"] = json.loads(str(data.pop("cadence_json")))
    recipients = data.pop("recipients_json")
    data["recipients"] = json.loads(str(recipients)) if recipients else None
    data["enabled"] = bool(data["enabled"])
    return Schedule.model_validate(data)


def run_row(r: ScheduleRun) -> Row:
    return (
        r.id, r.schedule_id, ts(r.slot_at), r.trigger.value, r.state.value, ts(r.started_at),
        ts(r.finished_at), r.job_id, r.analysis_id, r.risk_score,
        r.risk_level.value if r.risk_level else None,
        None if r.rto_feasible is None else int(r.rto_feasible),
        r.email_state.value if r.email_state else None,
        ",".join(r.email_to) or None, r.error_code, r.error,
    )  # fmt: skip


def run_from_row(row: Row) -> ScheduleRun:
    return ScheduleRun.model_validate(
        {
            "id": row[0],
            "schedule_id": row[1],
            "slot_at": row[2],
            "trigger": row[3],
            "state": row[4],
            "started_at": row[5],
            "finished_at": row[6],
            "job_id": row[7],
            "analysis_id": row[8],
            "risk_score": row[9],
            "risk_level": row[10],
            "rto_feasible": None if row[11] is None else bool(row[11]),
            "email_state": row[12],
            "email_to": str(row[13]).split(",") if row[13] else [],
            "error_code": row[14],
            "error": row[15],
        }
    )


def state_from_row(row: Row) -> SchedulerState:
    return SchedulerState.model_validate(
        {"paused": bool(row[0]), "pause_until": row[1], "paused_by": row[2], "paused_at": row[3]}
    )


def state_row(state: SchedulerState) -> Row:
    return (int(state.paused), ts(state.pause_until), state.paused_by, ts(state.paused_at))
