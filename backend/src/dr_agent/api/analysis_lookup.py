"""Finished analyses for the routes: in memory first, then the history (ADR 0007).

After a restart a job is gone from memory, but its stored analysis can still be
polled, exported and executed. `history_saver()` is the `JobStore` hook that
stores each finished job.
"""

from __future__ import annotations

from dataclasses import dataclass

from dr_agent.api.deps import AppState
from dr_agent.api.jobs import Job, OnSuccess
from dr_agent.api.schemas import JobState, JobView
from dr_agent.history.models import AnalysisRecord, AnalysisSource, Provenance
from dr_agent.history.service import History
from dr_agent.models.report import DRReadinessReport
from dr_agent.models.runbook import Runbook
from dr_agent.utils.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class FinishedAnalysis:
    id: str
    runbook: Runbook
    runbook_label: str
    report: DRReadinessReport


def history_saver(history: History, provenance: Provenance) -> OnSuccess:
    async def save(job: Job) -> bool:
        if job.report is None or job.runbook is None or job.completed_at is None:
            return False  # pragma: no cover - JobStore calls this only with a report
        record = AnalysisRecord(
            id=job.id,
            source=AnalysisSource.API,
            created_at=job.created_at,
            completed_at=job.completed_at,
            runbook_label=job.runbook_label,
            runbook=job.runbook,
            inventory_label=job.inventory_label,
            inventory=job.inventory,
            report=job.report,
            provenance=provenance,
        )
        return await history.save(record)

    return save


async def job_view(state: AppState, job_id: str) -> tuple[Job | None, JobView]:
    """The live job and its view, or (None, view of the stored analysis)."""
    try:
        job = state.jobs.get(job_id)
    except NotFoundError:
        record = await _stored(state, job_id)
        return None, JobView(
            job_id=record.id,
            status=JobState.SUCCEEDED,
            created_at=record.created_at,
            completed_at=record.completed_at,
            report=record.report,
            history_saved=True,
        )
    return job, job.view()


async def finished_analysis(state: AppState, analysis_id: str) -> FinishedAnalysis:
    """A succeeded analysis; `409` while unfinished or failed, `404` if unknown."""
    try:
        job = state.jobs.get(analysis_id)
    except NotFoundError:
        record = await _stored(state, analysis_id)
        return FinishedAnalysis(record.id, record.runbook, record.runbook_label, record.report)
    if job.state is not JobState.SUCCEEDED or job.report is None or job.runbook is None:
        raise ConflictError(
            "the analysis has not finished successfully", details={"status": job.state.value}
        )
    return FinishedAnalysis(job.id, job.runbook, job.runbook_label, job.report)


async def _stored(state: AppState, analysis_id: str) -> AnalysisRecord:
    if state.history is None:
        raise NotFoundError(f"unknown job id: {analysis_id}")
    try:
        return await state.history.store.get(analysis_id)
    except NotFoundError:
        raise NotFoundError(f"unknown job id: {analysis_id}") from None
