"""Checks one tool call against the policy and the server's tool catalog.

Order: allow-list, offered by the server, arguments against the tool's
`inputSchema`, then policy constraints. The risk class comes from the policy
and may only be raised by the server's hints, never lowered (ADR 0006).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import JsonValue

from dr_agent.execution.models import RiskClass
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.models.runbook import PlannedToolCall
from dr_agent.tools.base import ToolSpec
from dr_agent.utils.errors import PolicyViolationError

Catalog = Mapping[tuple[str, str], ToolSpec]

REQUIRED_APPROVALS: dict[RiskClass, int] = {
    RiskClass.READ: 1,
    RiskClass.WRITE: 1,
    RiskClass.DESTRUCTIVE: 2,
}
_RANK = {RiskClass.READ: 0, RiskClass.WRITE: 1, RiskClass.DESTRUCTIVE: 2}
_MAX_MESSAGE = 200


def index_catalog(specs: Iterable[ToolSpec]) -> dict[tuple[str, str], ToolSpec]:
    return {(spec.server, spec.name): spec for spec in specs}


def check_call(policy: ExecutionPolicy, catalog: Catalog, call: PlannedToolCall) -> RiskClass:
    """The call's effective risk class, or `PolicyViolationError` listing every problem."""
    name = f"{call.server}/{call.tool}"
    tool_policy = policy.tool(call.server, call.tool)
    if tool_policy is None:
        raise _violation(name, ["tool is not allow-listed in the execution policy"])
    spec = catalog.get((call.server, call.tool))
    if spec is None:
        raise _violation(name, ["tool is not offered by the server"])

    problems = _schema_problems(spec.input_schema, call.arguments)
    for argument, schema in sorted(tool_policy.constraints.items()):
        if argument not in call.arguments:
            problems.append(f"{argument}: required by the policy constraint")
            continue
        problems.extend(
            f"{argument}: {message}" for message in _messages(schema, call.arguments[argument])
        )
    if problems:
        raise _violation(name, problems)
    return effective_risk(tool_policy.risk, spec)


def check_verify_call(
    policy: ExecutionPolicy, catalog: Catalog, call: PlannedToolCall
) -> RiskClass:
    """Verify calls run under the main call's approval, so they must be read-only."""
    risk = check_call(policy, catalog, call)
    if risk is not RiskClass.READ:
        raise _violation(f"{call.server}/{call.tool}", ["verify calls must be read-only tools"])
    return risk


def effective_risk(policy_risk: RiskClass, spec: ToolSpec) -> RiskClass:
    hinted = policy_risk
    if spec.destructive_hint is True:
        hinted = RiskClass.DESTRUCTIVE
    elif spec.read_only_hint is False:
        hinted = RiskClass.WRITE
    return max(policy_risk, hinted, key=_RANK.__getitem__)


def _schema_problems(schema: dict[str, JsonValue], arguments: dict[str, JsonValue]) -> list[str]:
    try:
        validator_for(schema, default=Draft202012Validator).check_schema(schema)
    except SchemaError:
        return ["the server's input schema for this tool is invalid"]
    return [f"arguments: {message}" for message in _messages(schema, arguments)]


def _messages(schema: dict[str, JsonValue], instance: JsonValue) -> list[str]:
    validator = validator_for(schema, default=Draft202012Validator)(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda err: list(map(str, err.path)))
    return [
        ("/".join(map(str, err.path)) + ": " if err.path else "") + err.message[:_MAX_MESSAGE]
        for err in errors
    ]


def _violation(name: str, problems: list[str]) -> PolicyViolationError:
    return PolicyViolationError(
        f"{name} is not allowed: {problems[0]}", details={"tool": name, "problems": problems}
    )
