"""In-memory analysis job store.

Analysis on a CPU-only local LLM takes minutes, so the API queues a job and
returns its id (plan decision D3). A semaphore caps concurrent analyses (the
model server handles one at a time anyway); finished jobs are evicted oldest
first once `max_stored` is reached, and new work is refused with
`CapacityError` when that many jobs are still unfinished. Jobs live in
memory; a finished report is handed to the injected `on_success` hook (the
analysis history, ADR 0007) before the job is marked succeeded, so a client
never sees a succeeded job that is not stored yet.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dr_agent.api.errors import json_safe
from dr_agent.api.schemas import ErrorBody, JobState, JobView
from dr_agent.models.inventory import SystemInventory
from dr_agent.models.report import DRReadinessReport
from dr_agent.models.runbook import Runbook
from dr_agent.utils.errors import AppError, CapacityError, NotFoundError
from dr_agent.utils.logging import get_logger

Work = Callable[[], Awaitable[DRReadinessReport]]
OnSuccess = Callable[["Job"], Awaitable[bool]]

_log = get_logger("dr_agent.api.jobs")
_INTERNAL_ERROR = ErrorBody(error="internal error during analysis", code="INTERNAL_ERROR")
_CANCELLED = ErrorBody(error="job cancelled (server shutting down)", code="CANCELLED")


@dataclass
class Job:
    id: str
    created_at: datetime
    state: JobState = JobState.PENDING
    completed_at: datetime | None = None
    report: DRReadinessReport | None = None
    error: ErrorBody | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    # Kept so an execution can be created from this analysis (never sent to clients).
    runbook: Runbook | None = None
    runbook_label: str = "runbook.md"
    inventory: SystemInventory | None = None
    inventory_label: str | None = None
    history_saved: bool | None = None  # None while history is off or the job is unfinished

    def view(self) -> JobView:
        return JobView(
            job_id=self.id,
            status=self.state,
            created_at=self.created_at,
            completed_at=self.completed_at,
            report=self.report,
            error=self.error,
            history_saved=self.history_saved,
        )


class JobStore:
    def __init__(
        self,
        *,
        max_concurrent: int,
        max_stored: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        on_success: OnSuccess | None = None,
    ) -> None:
        self._jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_stored = max_stored
        self._clock = clock
        self._id_factory = id_factory
        self._on_success = on_success

    def submit(
        self,
        work: Work,
        *,
        runbook: Runbook | None = None,
        label: str = "runbook.md",
        inventory: SystemInventory | None = None,
        inventory_label: str | None = None,
    ) -> Job:
        self._evict_finished()
        if len(self._jobs) >= self._max_stored:
            raise CapacityError(
                "too many unfinished analysis jobs; retry later",
                details={"maxStoredJobs": self._max_stored},
            )
        job = Job(
            id=self._id_factory(),
            created_at=self._clock(),
            runbook=runbook,
            runbook_label=label,
            inventory=inventory,
            inventory_label=inventory_label,
        )
        self._jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job, work), name=f"analysis-{job.id}")
        return job

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"unknown job id: {job_id}")
        return job

    async def wait(self, job: Job, timeout_seconds: float) -> None:
        """Wait up to `timeout_seconds` for the job to finish; returns either way."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(job.done.wait(), timeout_seconds)

    async def shutdown(self) -> None:
        """Cancel unfinished jobs and wait for them to unwind (graceful shutdown)."""
        tasks = [job.task for job in self._jobs.values() if job.task and not job.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, job: Job, work: Work) -> None:
        try:
            async with self._semaphore:
                job.state = JobState.RUNNING
                job.report = await work()
            job.completed_at = self._clock()
            if self._on_success is not None:
                job.history_saved = await self._on_success(job)
            job.state = JobState.SUCCEEDED
        except AppError as exc:
            job.state, job.error = (
                JobState.FAILED,
                ErrorBody.model_validate(json_safe(exc.to_dict())),
            )
        except asyncio.CancelledError:
            job.state, job.error = JobState.FAILED, _CANCELLED
            raise
        except Exception:  # background task boundary: record, never lose the error
            _log.exception("analysis_job_failed", job_id=job.id)
            job.state, job.error = JobState.FAILED, _INTERNAL_ERROR
        finally:
            job.completed_at = job.completed_at or self._clock()
            job.done.set()

    def _evict_finished(self) -> None:
        finished = [job_id for job_id, job in self._jobs.items() if job.done.is_set()]
        overflow = len(self._jobs) - self._max_stored + 1
        for job_id in finished[: max(0, overflow)]:
            del self._jobs[job_id]
