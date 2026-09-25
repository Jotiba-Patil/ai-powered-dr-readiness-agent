"""Policy evaluation for the calls attached to one step (main, verify, rollback)."""

from __future__ import annotations

from dr_agent.execution.models import CallKind, StepRun, ToolCall
from dr_agent.execution.policy import Catalog, check_call, check_verify_call
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.utils.errors import PolicyViolationError


def evaluate_step_calls(run: StepRun, policy: ExecutionPolicy, catalog: Catalog) -> list[str]:
    """Sets each call's risk class; returns the problems (empty when all calls pass)."""
    problems: list[str] = []
    for call in (run.call, run.verify, run.rollback):
        if call is not None:
            problems.extend(_evaluate(call, policy, catalog))
    return problems


def _evaluate(call: ToolCall, policy: ExecutionPolicy, catalog: Catalog) -> list[str]:
    check = check_verify_call if call.kind is CallKind.VERIFY else check_call
    try:
        call.risk_class = check(policy, catalog, call.planned())
    except PolicyViolationError as exc:
        call.risk_class = None
        return [f"{call.kind.value}: {exc.message}"]
    return []
