"""User actions on schedules: create, update, pause, pause until, pause all, run now."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from scheduling_support import T0, daily, hourly, make_rig

from dr_agent.scheduling.models import RunTrigger
from dr_agent.scheduling.service import Limits
from dr_agent.utils.errors import ConflictError, NotFoundError, PathNotAllowedError, ValidationError


async def test_create_sets_the_first_slot(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    schedule = await rig.service.create(
        daily(timezone="Europe/Berlin"), created_by="  Alice   Chen "
    )
    assert schedule.id == "s1"
    assert schedule.created_by == "Alice Chen"
    assert schedule.next_run_at == T0 + timedelta(days=1, hours=-1)  # 06:00 CEST on 28 Sep
    assert await rig.store.get("s1") == schedule


@pytest.mark.parametrize(
    ("runbook", "inventory", "error"),
    [
        ("../pyproject.toml", None, PathNotAllowedError),
        ("runbooks/estimate-service.md", "../secrets.json", PathNotAllowedError),
        ("inventories/healthy.json", None, PathNotAllowedError),  # wrong suffix
        ("runbooks/missing.md", None, NotFoundError),
    ],
)
async def test_paths_are_checked_when_saved(
    tmp_path: Path, runbook: str, inventory: str | None, error: type[Exception]
) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    with pytest.raises(error):
        await rig.service.create(
            hourly(runbook_path=runbook, inventory_path=inventory), created_by="A"
        )
    assert await rig.store.list_all() == []


async def test_schedule_limit_and_names(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite", limits=Limits(max_schedules=1))
    await rig.service.create(hourly(), created_by="Alice")
    with pytest.raises(ConflictError, match="too many schedules"):
        await rig.service.create(hourly(), created_by="Alice")
    with pytest.raises(ValidationError):
        await rig.service.pause("s1", by="   ")
    with pytest.raises(ValidationError):
        await rig.service.pause("s1", by="x" * 101)


async def test_update_recomputes_the_next_slot_and_keeps_a_pause(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await rig.service.create(hourly(), created_by="Alice")
    changed = await rig.service.update("s1", daily("07:00"))
    assert changed.name == "Estimate daily"
    assert changed.next_run_at == T0 + timedelta(hours=2)
    assert changed.created_by == "Alice"
    await rig.service.pause("s1", by="Bob")
    still_paused = await rig.service.update("s1", hourly())
    assert (still_paused.enabled, still_paused.next_run_at) == (False, None)


async def test_pause_and_resume_skip_missed_slots(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await rig.service.create(hourly(), created_by="Alice")
    paused = await rig.service.pause("s1", by="Bob")
    assert (paused.enabled, paused.next_run_at, paused.paused_by) == (False, None, "Bob")
    assert paused.paused_at == T0
    rig.clock.advance(hours=5)
    assert await rig.scheduler.tick() == []
    resumed = await rig.service.resume("s1", by="Bob")
    assert resumed.enabled
    assert resumed.paused_by is None
    assert resumed.next_run_at == T0 + timedelta(hours=5, minutes=15)


async def test_pause_until_is_validated_and_expires(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite", limits=Limits(max_pause_days=2))
    await rig.service.create(hourly(), created_by="Alice")
    with pytest.raises(ValidationError, match="future"):
        await rig.service.pause("s1", by="Bob", until=T0)
    with pytest.raises(ValidationError, match="at most 2 days"):
        await rig.service.pause("s1", by="Bob", until=T0 + timedelta(days=2, seconds=1))
    until = T0 + timedelta(hours=3)
    assert (await rig.service.pause("s1", by="Bob", until=until)).pause_until == until
    rig.clock.advance(hours=3, minutes=1)
    assert await rig.scheduler.tick() == []  # resumes now, first slot after resuming is 08:15
    assert (await rig.store.get("s1")).next_run_at == T0 + timedelta(hours=3, minutes=15)


async def test_pause_all_and_resume_all(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await rig.service.create(hourly(), created_by="Alice")
    with pytest.raises(ValidationError):
        await rig.service.pause_all(by="Bob", until=T0 - timedelta(minutes=1))
    state = await rig.service.pause_all(by="Bob", until=T0 + timedelta(days=1))
    assert (state.paused, state.paused_by) == (True, "Bob")
    rig.clock.advance(hours=2)
    assert await rig.scheduler.tick() == []
    state = await rig.service.resume_all(by="Bob")
    assert not state.paused
    assert (await rig.store.get("s1")).next_run_at == T0 + timedelta(hours=2, minutes=15)


async def test_run_now_works_while_paused_but_not_twice(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    rig.analyze.gate = None
    await rig.service.create(hourly(), created_by="Alice")
    await rig.service.pause("s1", by="Bob")
    run = await rig.service.run_now("s1")
    assert run.trigger is RunTrigger.MANUAL
    with pytest.raises(ConflictError):
        await rig.service.run_now("s1")
    await rig.scheduler.wait_idle()
    with pytest.raises(ConflictError, match="already exists"):  # same instant as the first run
        await rig.service.run_now("s1")
    rig.clock.advance(seconds=1)
    assert (await rig.service.run_now("s1")).id != run.id
    await rig.scheduler.wait_idle()
