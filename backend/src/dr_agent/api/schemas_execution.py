"""Request and response models for the execution API (design section 8).

Bodies are validated here; the engine validates again (names, reasons, the
call hash) because the CLI reaches it without going through the API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from dr_agent.execution.audit import AuditEvent, ChainVerification
from dr_agent.execution.models import (
    CallKind,
    Execution,
    ExecutionMode,
    ExecutionState,
    RiskClass,
)
from dr_agent.models.base import CamelModel
from dr_agent.models.runbook import PlannedToolCall

Name = Field(min_length=1, max_length=100)
Text = Field(default=None, max_length=500)


class CreateExecutionRequest(CamelModel):
    """An execution is always created from a finished readiness analysis."""

    analysis_job_id: str = Field(
        pattern=r"^[A-Za-z0-9_-]{1,64}$", description="A succeeded analysis job"
    )
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    started_by: str = Name


class LifecycleRequest(CamelModel):
    """`pause`, `abort` and `close` need a reason; `start` and `resume` do not."""

    actor: str = Name
    reason: str | None = Text


class ApproveRequest(CamelModel):
    approver: str = Name
    call_hash: str = Field(pattern=r"^[0-9a-f]{64}$", description="The hash the approver was shown")
    comment: str | None = Text
    kind: Literal[CallKind.MAIN, CallKind.ROLLBACK] = CallKind.MAIN


class CallRequest(CamelModel):
    """Replace a call, or accept it as it is (`call` omitted on the main call)."""

    editor: str = Name
    kind: CallKind = CallKind.MAIN
    call: PlannedToolCall | None = None


class StepDecisionRequest(CamelModel):
    """`reject`, `skip` and `manual` need a reason; `verify` needs `succeeded`."""

    actor: str = Name
    reason: str | None = Text
    succeeded: bool | None = None


class ExecutionSummary(CamelModel):
    id: str
    analysis_job_id: str | None
    state: ExecutionState
    mode: ExecutionMode
    runbook_label: str
    started_by: str
    created_at: datetime
    updated_at: datetime
    steps: int

    @classmethod
    def of(cls, execution: Execution) -> ExecutionSummary:
        return cls(
            id=execution.id,
            analysis_job_id=execution.analysis.job_id if execution.analysis else None,
            state=execution.state,
            mode=execution.mode,
            runbook_label=execution.runbook_label,
            started_by=execution.started_by,
            created_at=execution.created_at,
            updated_at=execution.updated_at,
            steps=len(execution.steps),
        )


class ExecutionSettingsView(CamelModel):
    enabled: bool
    allow_live: bool
    approval_timeout_minutes: float
    max_tool_calls: int
    approvals_by_risk: dict[RiskClass, int]
    identity_verified: Literal[False] = False


class ToolView(CamelModel):
    server: str
    name: str
    description: str
    risk: RiskClass
    input_schema: dict[str, JsonValue]


class AuditView(CamelModel):
    events: list[AuditEvent]
    verification: ChainVerification | None = None
