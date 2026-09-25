"""The sub-schema the LLM is asked to produce: reasoning-heavy sections only.

Deterministic facts (RTO math, dependency health, execution phases, four
rule-checkable gap types) are computed in `core/` and never asked of the model.
"""

from __future__ import annotations

from pydantic import Field

from dr_agent.models.base import CamelModel
from dr_agent.models.report import Gap, SinglePointOfFailure, Suggestion


class StepDependency(CamelModel):
    step_number: int = Field(ge=1)
    depends_on: list[int] = Field(
        default_factory=list, description="Step numbers this step needs first"
    )


class LlmAnalysis(CamelModel):
    step_dependencies: list[StepDependency] = Field(default_factory=list)
    single_points_of_failure: list[SinglePointOfFailure] = Field(default_factory=list)
    gap_analysis: list[Gap] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    summary: str = Field(min_length=1, description="2-3 paragraph executive summary")
    risk_score: int = Field(ge=0, le=100, strict=True, description="Proposed 0-100 risk score")
