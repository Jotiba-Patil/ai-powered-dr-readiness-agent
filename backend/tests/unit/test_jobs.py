import asyncio
from datetime import UTC, datetime
from itertools import count

import pytest

from dr_agent.api.jobs import Job, JobStore
from dr_agent.api.schemas import JobState
from dr_agent.models.report import DRReadinessReport
from dr_agent.utils.errors import CapacityError, NotFoundError, ParseError

FIXED = datetime(2026, 9, 23, tzinfo=UTC)


def _store(max_stored: int = 10, max_concurrent: int = 1) -> JobStore:
    ids = count(1)
    return JobStore(
        max_concurrent=max_concurrent,
        max_stored=max_stored,
        clock=lambda: FIXED,
        id_factory=lambda: f"job{next(ids)}",
    )


async def test_successful_job_stores_report(sample_report: DRReadinessReport) -> None:
    store = _store()

    async def work() -> DRReadinessReport:
        return sample_report

    job = store.submit(work)
    assert job.state is JobState.PENDING
    await store.wait(job, 1)
    assert job.state is JobState.SUCCEEDED
    assert store.get("job1").view().report == sample_report
    assert job.completed_at == FIXED


async def test_report_is_handed_to_history_before_success(
    sample_report: DRReadinessReport,
) -> None:
    seen: list[tuple[JobState, bool]] = []

    async def on_success(job: Job) -> bool:
        seen.append((job.state, job.report is sample_report))
        return True

    store = JobStore(max_concurrent=1, max_stored=5, clock=lambda: FIXED, on_success=on_success)

    async def work() -> DRReadinessReport:
        return sample_report

    job = store.submit(work, label="x.md", inventory_label="inv.json")
    await store.wait(job, 1)
    assert seen == [(JobState.RUNNING, True)]
    assert (job.state, job.history_saved, job.view().history_saved) == (
        JobState.SUCCEEDED,
        True,
        True,
    )
    assert job.inventory_label == "inv.json"


async def test_app_error_becomes_failed_job_with_error_shape() -> None:
    store = _store()

    async def work() -> DRReadinessReport:
        raise ParseError("bad runbook", details={"why": ValueError("x")})

    job = store.submit(work)
    await store.wait(job, 1)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert job.error.code == "PARSE_ERROR"
    assert job.error.details == {"why": "x"}


async def test_unexpected_error_is_recorded_not_lost() -> None:
    store = _store()

    async def work() -> DRReadinessReport:
        raise RuntimeError("boom")

    job = store.submit(work)
    await store.wait(job, 1)
    assert job.error is not None
    assert job.error.code == "INTERNAL_ERROR"


async def test_wait_returns_on_timeout_and_shutdown_cancels() -> None:
    store = _store()
    gate = asyncio.Event()

    async def work() -> DRReadinessReport:
        await gate.wait()
        raise AssertionError("never released")

    job = store.submit(work)
    await store.wait(job, 0.01)
    assert job.state is JobState.RUNNING
    await store.shutdown()
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert job.error.code == "CANCELLED"


async def test_semaphore_keeps_second_job_pending(sample_report: DRReadinessReport) -> None:
    store = _store(max_concurrent=1)
    gate = asyncio.Event()

    async def slow() -> DRReadinessReport:
        await gate.wait()
        return sample_report

    first, second = store.submit(slow), store.submit(slow)
    await store.wait(first, 0.01)
    assert (first.state, second.state) == (JobState.RUNNING, JobState.PENDING)
    gate.set()
    await store.wait(second, 1)
    assert second.state is JobState.SUCCEEDED


async def test_capacity_error_when_all_stored_jobs_unfinished() -> None:
    store = _store(max_stored=1)
    gate = asyncio.Event()

    async def slow() -> DRReadinessReport:
        await gate.wait()
        raise AssertionError("unreachable")

    store.submit(slow)
    with pytest.raises(CapacityError):
        store.submit(slow)
    await store.shutdown()


async def test_finished_jobs_are_evicted_oldest_first(sample_report: DRReadinessReport) -> None:
    store = _store(max_stored=2)

    async def work() -> DRReadinessReport:
        return sample_report

    for _ in range(3):
        await store.wait(store.submit(work), 1)
    with pytest.raises(NotFoundError):
        store.get("job1")
    assert store.get("job3").state is JobState.SUCCEEDED


def test_unknown_job_raises_not_found() -> None:
    with pytest.raises(NotFoundError):
        _store().get("missing")
