"""API request/response models (validated at the boundary, camelCase on the wire)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from dr_agent.models.base import CamelModel
from dr_agent.models.inventory import SystemInventory
from dr_agent.models.report import DRReadinessReport


class AnalyzeJsonRequest(CamelModel):
    """JSON form of `POST /api/v1/dr/analyze` (the brief's `{ runbookMarkdown, inventory? }`)."""

    runbook_markdown: str = Field(min_length=1, description="The runbook as Markdown text.")
    inventory: SystemInventory | None = None
    runbook_name: str | None = Field(
        default=None, max_length=255, description="Label for report meta.runbookFile."
    )


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ErrorBody(CamelModel):
    """The shared error shape: `{error, code, details?}`."""

    error: str
    code: str
    details: dict[str, object] | None = None


class JobView(CamelModel):
    job_id: str
    status: JobState
    created_at: datetime
    completed_at: datetime | None = None
    report: DRReadinessReport | None = None
    error: ErrorBody | None = None
    history_saved: bool | None = Field(
        default=None, description="Whether the report was stored (null while history is off)"
    )


class HealthResponse(CamelModel):
    status: Literal["ok"] = "ok"
    version: str
    uptime: float = Field(ge=0, description="Seconds since the API started.")


class SampleList(CamelModel):
    """Paths relative to `API_ALLOWED_DIR`, usable with `GET /api/v1/dr/analyze`."""

    runbooks: list[str]
    inventories: list[str]


class SampleFile(CamelModel):
    path: str
    content: str
