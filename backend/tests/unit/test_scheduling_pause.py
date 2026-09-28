"""Store-level pausing: one schedule until a date, everything, and resuming from now."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from scheduling_support import T0, ids
from test_scheduling_store import schedule, store_with

from dr_agent.scheduling.models import SchedulerState
from dr_agent.scheduling.runner import next_slot


async def test_paused_schedule_is_not_claimed_and_resumes_after_pause_until(tmp_path: Path) -> None:
    until = T0 + timedelta(hours=2)
    paused = schedule(
        enabled=False, next_run_at=None, pause_until=until, paused_by="Bob", paused_at=T0
    )
    store = await store_with(tmp_path, paused)
    new_id = ids("r")
    assert await store.claim_due(T0 + timedelta(hours=1), next_slot, new_id) == []
    assert await store.claim_due(until + timedelta(minutes=1), next_slot, new_id) == []
    resumed = await store.get("s1")
    assert resumed.enabled
    assert resumed.pause_until is None
    assert resumed.paused_by is None
    assert resumed.next_run_at == T0 + timedelta(hours=2, minutes=15)  # first slot after resume


async def test_global_pause_blocks_everything_until_it_expires(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule())
    until = T0 + timedelta(hours=3)
    await store.pause_all(
        SchedulerState(paused=True, pause_until=until, paused_by="Bob", paused_at=T0)
    )
    assert (await store.get_state()).paused_by == "Bob"
    new_id = ids("r")
    assert await store.claim_due(T0 + timedelta(hours=2), next_slot, new_id) == []
    assert await store.claim_due(until + timedelta(minutes=1), next_slot, new_id) == []
    assert await store.get_state() == SchedulerState()
    assert (await store.get("s1")).next_run_at == T0 + timedelta(hours=3, minutes=15)


async def test_resume_all_restarts_from_now(tmp_path: Path) -> None:
    store = await store_with(tmp_path, schedule(), schedule("s2", enabled=False, next_run_at=None))
    await store.pause_all(SchedulerState(paused=True, paused_by="Bob", paused_at=T0))
    assert await store.claim_due(T0 + timedelta(days=2), next_slot, ids("r")) == []
    now = T0 + timedelta(days=2, minutes=20)
    await store.resume_all(now, next_slot)
    assert not (await store.get_state()).paused
    assert (await store.get("s1")).next_run_at == now + timedelta(minutes=55)
    assert (await store.get("s2")).next_run_at is None  # still paused on its own
