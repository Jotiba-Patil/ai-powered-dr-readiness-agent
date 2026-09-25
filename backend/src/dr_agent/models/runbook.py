"""Runbook, Step and Dependency models (output of the parser)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, JsonValue, model_validator

from dr_agent.models.base import CamelModel


class DependencyType(StrEnum):
    DATABASE = "database"
    MESSAGING = "messaging"
    SECRETS = "secrets"
    COMPUTE = "compute"
    NETWORK = "network"
    EXTERNAL = "external"
    OTHER = "other"


class Dependency(CamelModel):
    name: str = Field(min_length=1, description="Dependency name as written in the runbook")
    type: DependencyType = DependencyType.OTHER
    critical: bool = False


class PlannedToolCall(CamelModel):
    """A tool call written in a runbook annotation: `<server>/<tool> {JSON arguments}`.

    Untrusted input like any other runbook text: it is only a request, checked
    against the execution policy and approved by humans before anything runs.
    """

    server: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    tool: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class Step(CamelModel):
    step_number: int = Field(ge=1)
    action: str = Field(min_length=1)
    owner: str = Field(min_length=1, description="Person or team; 'team' is flagged as ambiguous")
    target_system: str | None = None
    estimated_minutes: float = Field(gt=0)
    validation_command: str | None = None
    depends_on: list[int] = Field(
        default_factory=list, description="Step numbers this step needs first (inferred by AI)"
    )
    tool_call: PlannedToolCall | None = None
    verify_call: PlannedToolCall | None = None
    rollback_call: PlannedToolCall | None = None


class Runbook(CamelModel):
    service_name: str = Field(min_length=1)
    system_owner: str = Field(min_length=1)
    rto_minutes: float = Field(gt=0)
    rpo_minutes: float = Field(gt=0)
    dependencies: list[Dependency] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    raw_markdown: str
    parser_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_step_graph(self) -> Runbook:
        numbers = [step.step_number for step in self.steps]
        if len(set(numbers)) != len(numbers):
            raise ValueError("step numbers must be unique")
        known = set(numbers)
        for step in self.steps:
            for dep in step.depends_on:
                if dep == step.step_number:
                    raise ValueError(f"step {step.step_number} cannot depend on itself")
                if dep not in known:
                    raise ValueError(f"step {step.step_number} depends on unknown step {dep}")
        return self
