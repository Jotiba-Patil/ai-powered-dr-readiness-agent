"""The scheduler: claims due slots and runs each one as analysis + email (ADR 0010).

It only analyzes. It never imports `execution/` and never creates an execution;
a person starts one from the stored analysis with the existing endpoint. Each
run is its own task so it can be cancelled; the ticker runs `tick()` first and
then sleeps, so a slot missed while the server was down runs once at startup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from dr_agent.models.report import DRReadinessReport
from dr_agent.scheduling.emailing import RunEmailer
from dr_agent.scheduling.models import RunState, Schedule, ScheduleRun
from dr_agent.scheduling.next_run import next_run_after
from dr_agent.scheduling.source import LoadedInput, RunbookSource
from dr_agent.scheduling.store import IdFactory, ScheduleStore
from dr_agent.utils.errors import AppError, ConflictError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.scheduling")
_MAX_ERROR = 300


@dataclass(frozen=True)
class AnalysisOutcome:
    """A finished analysis job: a report, or the error it failed with."""

    job_id: str
    report: DRReadinessReport | None
    stored: bool
    error_code: str | None = None
    error: str | None = None


# Submits the analysis and waits for it. When the awaiting task is cancelled it
# must cancel the analysis too (the API wires this to `JobStore.cancel`).
Analyze = Callable[[LoadedInput], Awaitable[AnalysisOutcome]]
Clock = Callable[[], datetime]


def next_slot(schedule: Schedule, after: datetime) -> datetime:
    return next_run_after(schedule.cadence, schedule.timezone, after)


class Scheduler:
    def __init__(
        self,
        store: ScheduleStore,
        *,
        source: RunbookSource,
        analyze: Analyze,
        emailer: RunEmailer,
        clock: Clock,
        new_id: IdFactory,
        tick_seconds: float = 30.0,
    ) -> None:
        self.store = store
        self._source = source
        self._analyze = analyze
        self.emailer = emailer
        self._clock = clock
        self._new_id = new_id
        self._tick_seconds = tick_seconds
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._ticker: asyncio.Task[None] | None = None
        self._stopping = False

    async def recover(self) -> int:
        """At startup: runs left `running` by a stop can never finish; mark them failed."""
        return await self.store.fail_interrupted(self._clock())

    async def tick(self) -> list[ScheduleRun]:
        runs = await self.store.claim_due(self._clock(), next_slot, self._new_id)
        for run in runs:
            self._start(run)
        return runs

    async def run_now(self, schedule_id: str) -> ScheduleRun:
        run = await self.store.start_manual(schedule_id, self._clock(), self._new_id())
        self._start(run)
        return run

    async def cancel(self, run_id: str) -> ScheduleRun:
        run = await self.store.get_run(run_id)
        if run.state is not RunState.RUNNING:
            raise ConflictError(f"run {run_id} is not running")
        task = self._tasks.get(run_id)
        if task is None:  # not owned by this process: close it directly
            await self.store.save_run(self._cancelled(run))
        else:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return await self.store.get_run(run_id)

    async def wait_idle(self) -> None:
        """Wait for every run in progress (tests and shutdown)."""
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def start(self) -> None:
        self._ticker = asyncio.create_task(self._tick_forever(), name="scheduler-ticker")

    async def shutdown(self) -> None:
        self._stopping = True
        tasks = [*self._tasks.values(), *([self._ticker] if self._ticker else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _start(self, run: ScheduleRun) -> None:
        task = asyncio.create_task(self._execute(run), name=f"schedule-run-{run.id}")
        self._tasks[run.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run.id, None))
        _log.info("schedule_run_started", schedule_id=run.schedule_id, run_id=run.id)

    async def _execute(self, run: ScheduleRun) -> None:
        try:
            await self._run(run)
        except asyncio.CancelledError:
            closed = self._interrupted(run) if self._stopping else self._cancelled(run)
            await self.store.save_run(closed)
            _log.info("schedule_run_stopped", run_id=run.id, state=closed.state.value)
            raise

    async def _run(self, run: ScheduleRun) -> None:
        schedule = await self.store.get(run.schedule_id)
        loaded: LoadedInput | None = None
        report: DRReadinessReport | None = None
        try:
            loaded = await self._source.load(schedule.runbook_path, schedule.inventory_path)
            outcome = await self._analyze(loaded)
            report = outcome.report
            run = self._with_outcome(run, outcome)
        except AppError as exc:
            run = self._failed(run, exc.code, exc.message)
        except Exception:  # task boundary: record the failure, keep the scheduler running
            _log.exception("schedule_run_crashed", schedule_id=run.schedule_id, run_id=run.id)
            run = self._failed(run, "INTERNAL_ERROR", "internal error during the scheduled run")
        run = await self.emailer.send(run, schedule, loaded, report)
        await self.store.save_run(run)
        _log.info(
            "schedule_run_finished",
            schedule_id=run.schedule_id,
            run_id=run.id,
            state=run.state.value,
            email=run.email_state.value if run.email_state else None,
        )

    def _with_outcome(self, run: ScheduleRun, outcome: AnalysisOutcome) -> ScheduleRun:
        if outcome.report is None:
            failed = self._failed(run, outcome.error_code or "ANALYSIS_ERROR", outcome.error or "")
            return failed.model_copy(update={"job_id": outcome.job_id})
        report = outcome.report
        return run.model_copy(
            update={
                "state": RunState.SUCCEEDED,
                "finished_at": self._clock(),
                "job_id": outcome.job_id,
                "analysis_id": outcome.job_id if outcome.stored else None,
                "risk_score": report.risk_score,
                "risk_level": report.risk_level,
                "rto_feasible": report.rto_analysis.feasible,
            }
        )

    def _failed(self, run: ScheduleRun, code: str, message: str) -> ScheduleRun:
        return run.model_copy(
            update={
                "state": RunState.FAILED,
                "finished_at": self._clock(),
                "error_code": code,
                "error": message[:_MAX_ERROR] or None,
            }
        )

    def _cancelled(self, run: ScheduleRun) -> ScheduleRun:
        update = {"state": RunState.CANCELLED, "finished_at": self._clock(), "error_code": None}
        return run.model_copy(update=update)

    def _interrupted(self, run: ScheduleRun) -> ScheduleRun:
        return self._failed(run, "INTERRUPTED", "the server stopped while this run was going")

    async def _tick_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # a store hiccup must not stop scheduling for good
                _log.exception("scheduler_tick_failed")
            await asyncio.sleep(self._tick_seconds)
