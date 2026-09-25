"""Execution state: one `Execution` holding a `StepRun` per runbook step.

The whole document is saved together with its audit events (one transaction,
ADR 0004), so these models are the source of truth for an execution.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue

from dr_agent.execution.canonical import call_hash
from dr_agent.models.base import CamelModel
from dr_agent.models.runbook import PlannedToolCall
from dr_agent.tools.base import ToolResult
from dr_agent.utils.errors import NotFoundError


class ExecutionState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class StepState(StrEnum):
    PLANNED = "PLANNED"
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    ROLLED_BACK = "ROLLED_BACK"
    AWAITING_MANUAL = "AWAITING_MANUAL"
    MANUAL_DONE = "MANUAL_DONE"
    SKIPPED = "SKIPPED"


class RiskClass(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class CallSource(StrEnum):
    ANNOTATED = "annotated"
    AI_PROPOSED = "ai_proposed"
    EDITED = "edited"


class ExecutionMode(StrEnum):
    DRY_RUN = "dry_run"
    LIVE = "live"


class CallKind(StrEnum):
    MAIN = "main"
    VERIFY = "verify"
    ROLLBACK = "rollback"


Name = Field(min_length=1, max_length=100)


class Approval(CamelModel):
    approver: str = Name
    comment: str | None = Field(default=None, max_length=500)
    call_hash: str
    # A step's verify call runs under the main call's approval, so both hashes are bound.
    verify_hash: str | None = None
    created_at: datetime


class ToolCall(CamelModel):
    kind: CallKind
    server: str
    tool: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    source: CallSource
    risk_class: RiskClass | None = None
    call_hash: str
    approvals: list[Approval] = Field(default_factory=list)
    result: ToolResult | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_planned(cls, planned: PlannedToolCall, kind: CallKind, source: CallSource) -> ToolCall:
        return cls(
            kind=kind,
            server=planned.server,
            tool=planned.tool,
            arguments=planned.arguments,
            source=source,
            call_hash=call_hash(planned.server, planned.tool, planned.arguments),
        )

    def planned(self) -> PlannedToolCall:
        return PlannedToolCall(server=self.server, tool=self.tool, arguments=self.arguments)

    def reset_outcome(self) -> None:
        self.result, self.error, self.started_at, self.finished_at = None, None, None, None


class ProposalNote(CamelModel):
    """Why the model proposed a step's call; untrusted text, shown to reviewers as-is."""

    rationale: str = Field(default="", max_length=1000)
    confidence: str | None = None


class StepRun(CamelModel):
    step_number: int = Field(ge=1)
    phase: int = Field(ge=1)
    action: str
    owner: str
    target_system: str | None = None
    estimated_minutes: float
    depends_on: list[int] = Field(default_factory=list)
    state: StepState = StepState.PLANNED
    attempt: int = Field(default=1, ge=1)
    call: ToolCall | None = None
    verify: ToolCall | None = None
    rollback: ToolCall | None = None
    policy_errors: list[str] = Field(default_factory=list)
    summary: str | None = None
    proposal: ProposalNote | None = None
    waiting_since: datetime | None = None


class AnalysisRef(CamelModel):
    """The readiness analysis an execution was created from (API and CLI require one)."""

    job_id: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: str
    ai_analysis_available: bool
    analyzed_at: datetime


class Execution(CamelModel):
    id: str = Field(min_length=1)
    state: ExecutionState = ExecutionState.CREATED
    mode: ExecutionMode
    runbook_label: str
    runbook_sha256: str
    started_by: str = Name
    created_at: datetime
    updated_at: datetime
    steps: list[StepRun]
    tool_calls_used: int = 0
    pause_reason: str | None = None
    audit_seq: int = 0
    audit_head: str = ""
    analysis: AnalysisRef | None = None

    def step(self, step_number: int) -> StepRun:
        for run in self.steps:
            if run.step_number == step_number:
                return run
        raise NotFoundError(f"step {step_number} not found", details={"step": step_number})
