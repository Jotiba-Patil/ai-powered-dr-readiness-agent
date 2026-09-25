"""State and scenario models of the simulated DR environment (ADR 0005).

The default state is the estimate-service regional outage: the primary region
is down, the standby deployment is scaled down, the database replica is still
in recovery, the cache is cold and DNS points at the primary region. A scenario
file (`MOCK_MCP_SCENARIO`) may replace the state and inject faults per tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic import ValidationError as PydanticValidationError

from dr_agent.models.base import CamelModel
from dr_agent.utils.errors import ConfigError

Region = Literal["primary", "standby"]


class DeploymentState(CamelModel):
    revision: int = Field(default=7, ge=1)
    ready: bool = False
    previous: tuple[int, bool] | None = None  # (revision, ready) before the last restart


class DatabaseState(CamelModel):
    primary: bool = False  # False: a replica still in recovery


class CacheState(CamelModel):
    warm: bool = False
    snapshots: list[str] = Field(default_factory=lambda: ["latest"])


def _deployments() -> dict[str, dict[Region, DeploymentState]]:
    return {"estimate-service": {"primary": DeploymentState(), "standby": DeploymentState()}}


def _dns() -> dict[str, Region]:
    return {"estimate-service": "primary"}


class EnvironmentState(CamelModel):
    deployments: dict[str, dict[Region, DeploymentState]] = Field(default_factory=_deployments)
    databases: dict[str, DatabaseState] = Field(
        default_factory=lambda: {"estimate-postgres": DatabaseState()}
    )
    caches: dict[str, CacheState] = Field(default_factory=lambda: {"pricing-cache": CacheState()})
    dns: dict[str, Region] = Field(default_factory=_dns)


class ToolFault(CamelModel):
    """Makes a tool fail on the listed calls (1-based, counted per tool) and/or slow it down."""

    fail_on_calls: list[int] = Field(default_factory=list)
    fail_always: bool = False
    message: str = "simulated failure"
    latency_ms: int = Field(default=0, ge=0, le=600_000)

    def fails(self, call_number: int) -> bool:
        return self.fail_always or call_number in self.fail_on_calls


class Scenario(CamelModel):
    state: EnvironmentState = Field(default_factory=EnvironmentState)
    faults: dict[str, ToolFault] = Field(default_factory=dict)


def load_scenario(path: Path) -> Scenario:
    try:
        return Scenario.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except OSError as exc:
        raise ConfigError("mock MCP scenario cannot be read", details={"path": str(path)}) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "mock MCP scenario is not valid JSON", details={"reason": exc.msg}
        ) from exc
    except PydanticValidationError as exc:
        raise ConfigError(
            "mock MCP scenario is invalid", details={"errors": exc.errors(include_url=False)}
        ) from exc
