"""The scheduler's analyze callable: a normal analysis job, stored with `source=scheduled`.

Scheduled runs share `JobStore` with interactive analyses (the concurrency cap,
history saving and the knowledge base). A full store raises `CapacityError`,
which fails the run until the next slot. Cancelling the waiting task cancels
the job too, so a cancelled run never leaves an analysis running.
"""

from __future__ import annotations

import asyncio

from dr_agent.api.jobs import JobStore
from dr_agent.api.schemas import JobState
from dr_agent.health.base import HealthChecker
from dr_agent.history.models import AnalysisSource
from dr_agent.knowledge.service import KnowledgeBase
from dr_agent.llm.base import LLMProvider
from dr_agent.scheduling.runner import AnalysisOutcome, Analyze
from dr_agent.scheduling.source import LoadedInput
from dr_agent.service import analyze_runbook


def job_analyzer(
    jobs: JobStore,
    *,
    llm: LLMProvider,
    checker: HealthChecker,
    knowledge: KnowledgeBase | None,
) -> Analyze:
    async def analyze(loaded: LoadedInput) -> AnalysisOutcome:
        job = jobs.submit(
            lambda: analyze_runbook(
                loaded.runbook,
                loaded.inventory,
                llm=llm,
                checker=checker,
                runbook_label=loaded.runbook_label,
                inventory_label=loaded.inventory_label,
                knowledge=knowledge,
            ),
            runbook=loaded.runbook,
            label=loaded.runbook_label,
            inventory=loaded.inventory,
            inventory_label=loaded.inventory_label,
            source=AnalysisSource.SCHEDULED,
        )
        try:
            await job.done.wait()
        except asyncio.CancelledError:
            await jobs.cancel(job.id)
            raise
        if job.state is JobState.SUCCEEDED and job.report is not None:
            return AnalysisOutcome(job.id, job.report, stored=job.history_saved is True)
        code = job.error.code if job.error else "ANALYSIS_ERROR"
        message = job.error.error if job.error else None
        return AnalysisOutcome(job.id, None, stored=False, error_code=code, error=message)

    return analyze
