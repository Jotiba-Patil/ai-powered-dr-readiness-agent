"""Claiming due slots and restarting schedules, inside the caller's transaction.

Order on every tick (design section 5.2 and 6): a global pause stops everything
until it expires; expired per-schedule pauses resume from the next slot after
now (missed slots are skipped); then each due schedule gets one run and moves
on to its next slot. A schedule whose previous run is still going skips the slot.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from dr_agent.scheduling import sqlite_rows as sql
from dr_agent.scheduling.models import RunTrigger, Schedule, ScheduleRun
from dr_agent.scheduling.store import IdFactory, NextSlot
from dr_agent.storage.sqlite import timestamp
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.scheduling")


def claim_due(
    conn: sqlite3.Connection, now: datetime, next_slot: NextSlot, new_id: IdFactory
) -> list[ScheduleRun]:
    state = sql.state_from_row(conn.execute(sql.SELECT_STATE).fetchone())
    if state.paused:
        if state.pause_until is not None and state.pause_until <= now:
            restart_all(conn, now, next_slot)
            _log.info("scheduler_resumed", reason="pause_until reached")
        return []
    for schedule in _schedules(conn, sql.SELECT_EXPIRED_PAUSES, now):
        _resume(conn, schedule, now, next_slot)
    return [
        run
        for schedule in _schedules(conn, sql.SELECT_DUE, now)
        if (run := _claim(conn, schedule, now, next_slot, new_id)) is not None
    ]


def restart_all(conn: sqlite3.Connection, now: datetime, next_slot: NextSlot) -> None:
    """Clear the global pause; every active schedule continues from its next slot."""
    conn.execute(sql.UPDATE_STATE, (0, None, None, None))
    for schedule in _schedules(conn, sql.SELECT_ACTIVE, None):
        conn.execute(sql.SET_NEXT_RUN, (timestamp(next_slot(schedule, now)), None, schedule.id))


def _claim(
    conn: sqlite3.Connection,
    schedule: Schedule,
    now: datetime,
    next_slot: NextSlot,
    new_id: IdFactory,
) -> ScheduleRun | None:
    following = timestamp(next_slot(schedule, now))
    if conn.execute(sql.RUNNING_OF, (schedule.id,)).fetchone():
        conn.execute(sql.SET_NEXT_RUN, (following, None, schedule.id))
        _log.info("schedule_slot_skipped", schedule_id=schedule.id, reason="previous run going")
        return None
    slot = schedule.next_run_at or now
    run = ScheduleRun(
        id=new_id(),
        schedule_id=schedule.id,
        slot_at=slot,
        trigger=RunTrigger.SCHEDULED,
        started_at=now,
    )
    try:
        conn.execute(sql.INSERT_RUN, sql.run_row(run))
    except sqlite3.IntegrityError:  # the slot already has a run
        conn.execute(sql.SET_NEXT_RUN, (following, None, schedule.id))
        return None
    conn.execute(sql.SET_NEXT_RUN, (following, timestamp(now), schedule.id))
    return run


def _resume(
    conn: sqlite3.Connection, schedule: Schedule, now: datetime, next_slot: NextSlot
) -> None:
    resumed = schedule.model_copy(
        update={
            "enabled": True,
            "pause_until": None,
            "paused_by": None,
            "paused_at": None,
            "updated_at": now,
            "next_run_at": next_slot(schedule, now),
        }
    )
    row = sql.schedule_row(resumed)
    conn.execute(sql.UPDATE_SCHEDULE, (*row[1:], row[0]))
    _log.info("schedule_resumed", schedule_id=schedule.id, reason="pause_until reached")


def _schedules(conn: sqlite3.Connection, statement: str, now: datetime | None) -> list[Schedule]:
    params = (timestamp(now),) if now else ()
    return [sql.schedule_from_row(tuple(row)) for row in conn.execute(statement, params)]
