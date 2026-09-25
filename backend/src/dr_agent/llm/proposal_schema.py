"""`ToolProposal`: the only shape an LLM answer about a runbook step may take.

Either one call (`server`, `tool`, `arguments`, `rationale`, `confidence`) or
`{"manual": true, "reason": ...}`. Validated with Pydantic like every LLM
reply; the proposer then checks the call against the allow-list and schemas.
The rationale is shown to reviewers as plain text and never used for decisions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from dr_agent.models.base import CamelModel


class ToolProposal(CamelModel):
    manual: bool = False
    server: str | None = Field(default=None, max_length=64)
    tool: str | None = Field(default=None, max_length=128)
    arguments: dict[str, JsonValue] | None = None
    rationale: str = Field(default="", max_length=1000)
    confidence: Literal["low", "medium", "high"] = "low"
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _call_or_manual(self) -> ToolProposal:
        if not self.manual and (not self.server or not self.tool):
            raise ValueError("server and tool are required unless manual is true")
        return self
