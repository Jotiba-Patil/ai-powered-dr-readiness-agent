"""The execution policy file (`EXECUTION_POLICY_FILE`): allow-list, risk classes, constraints.

A tool that is not listed cannot be proposed, approved or called, even when a
server offers it (ADR 0006). Tool names that suggest a shell or command runner
are refused when the file is loaded, whatever risk they are given.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import Field, JsonValue, field_validator
from pydantic import ValidationError as PydanticValidationError

from dr_agent.execution.models import RiskClass
from dr_agent.models.base import CamelModel
from dr_agent.utils.errors import ConfigError

_SHELL_TOKENS = frozenset(
    {"shell", "sh", "bash", "zsh", "pwsh", "powershell", "cmd", "exec", "execute", "command"}
    | {"script", "eval", "subprocess", "system", "terminal"}
)


def looks_like_shell(tool_name: str) -> bool:
    return any(token in _SHELL_TOKENS for token in re.split(r"[._\-\s]+", tool_name.lower()))


class ToolPolicy(CamelModel):
    risk: RiskClass
    # Per-argument JSON Schema fragments, e.g. {"region": {"enum": ["primary", "standby"]}}.
    constraints: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)

    @field_validator("constraints")
    @classmethod
    def _valid_schemas(
        cls, value: dict[str, dict[str, JsonValue]]
    ) -> dict[str, dict[str, JsonValue]]:
        for name, schema in value.items():
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ValueError(f"constraint for '{name}' is not a valid JSON Schema") from exc
        return value


class ServerPolicy(CamelModel):
    tools: dict[str, ToolPolicy] = Field(default_factory=dict)

    @field_validator("tools")
    @classmethod
    def _no_shell_tools(cls, value: dict[str, ToolPolicy]) -> dict[str, ToolPolicy]:
        refused = sorted(name for name in value if looks_like_shell(name))
        if refused:
            raise ValueError(f"shell-like tools are never allowed: {', '.join(refused)}")
        return value


class ExecutionPolicy(CamelModel):
    servers: dict[str, ServerPolicy] = Field(default_factory=dict)

    def tool(self, server: str, tool: str) -> ToolPolicy | None:
        server_policy = self.servers.get(server)
        return server_policy.tools.get(tool) if server_policy else None


def parse_policy(text: str, *, source: str = "policy") -> ExecutionPolicy:
    try:
        return ExecutionPolicy.model_validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{source} is not valid JSON", details={"reason": exc.msg}) from exc
    except PydanticValidationError as exc:
        raise ConfigError(
            f"{source} is invalid", details={"errors": exc.errors(include_url=False)}
        ) from exc


def load_policy(path: Path) -> ExecutionPolicy:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            "execution policy file cannot be read", details={"path": str(path)}
        ) from exc
    return parse_policy(text, source=f"execution policy {path.name}")
