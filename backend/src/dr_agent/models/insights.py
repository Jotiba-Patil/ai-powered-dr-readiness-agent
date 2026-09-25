"""What past analyses and live runs of a service showed (design analysis-history section 9).

Every field is a number, an enum value, a timestamp, a step number or an
identifier that already comes from the runbook or inventory. No free text from
tool results, rationales or earlier reports is ever stored here (ADR 0009).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from dr_agent.models.base import CamelModel

FinishedState = Literal["COMPLETED", "FAILED", "ABORTED"]


class StepHistory(CamelModel):
    step_number: int = Field(ge=1, description="In the runbook it was matched to")
    fingerprint: str = Field(description="SHA-256 of the normalized action and target system")
    target_system: str | None = None
    estimated_minutes: float = Field(ge=0)
    live_runs: int = Field(ge=0)
    succeeded: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    rolled_back: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    manual_done: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    median_active_minutes: float | None = Field(
        default=None, description="Running (or manual) until the step's final state"
    )
    max_active_minutes: float | None = None
    median_elapsed_minutes: float | None = Field(
        default=None, description="Including approval waits after the run started"
    )


class ExecutionOutcome(CamelModel):
    execution_id: str
    state: FinishedState
    started_at: datetime
    elapsed_minutes: float = Field(ge=0)
    stated_rto_minutes: float = Field(gt=0)


class DependencyTrend(CamelModel):
    name: str
    analyses: int = Field(ge=0)
    up: int = Field(default=0, ge=0)
    down: int = Field(default=0, ge=0)
    unreachable: int = Field(default=0, ge=0)
    not_in_inventory: int = Field(default=0, ge=0)


class ServiceHistory(CamelModel):
    """Facts computed by code from stored analyses and live executions only."""

    service_name: str
    analyses_considered: int = Field(ge=0)
    live_runs: int = Field(ge=0)
    dry_runs: int = Field(ge=0, description="Counted but never measured")
    risk_scores: list[int] = Field(default_factory=list, description="Oldest first")
    executions: list[ExecutionOutcome] = Field(default_factory=list, description="Newest first")
    steps: list[StepHistory] = Field(default_factory=list)
    dependencies: list[DependencyTrend] = Field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.analyses_considered == 0 and self.live_runs == 0
