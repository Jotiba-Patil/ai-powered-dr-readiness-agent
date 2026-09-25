"""Policy: allow-list, input schema, constraints, risk from hints, and the policy file."""

import json
from pathlib import Path

import pytest
from exec_support import drsim_catalog, drsim_policy, drsim_policy_dict

from dr_agent.execution.models import RiskClass
from dr_agent.execution.policy import (
    REQUIRED_APPROVALS,
    check_call,
    check_verify_call,
    effective_risk,
    index_catalog,
)
from dr_agent.execution.policy_file import load_policy, looks_like_shell, parse_policy
from dr_agent.models.runbook import PlannedToolCall
from dr_agent.tools.base import ToolSpec
from dr_agent.utils.errors import ConfigError, PolicyViolationError

CATALOG = index_catalog(drsim_catalog())
POLICY = drsim_policy()


def _call(tool: str, **arguments: object) -> PlannedToolCall:
    return PlannedToolCall.model_validate({"server": "drsim", "tool": tool, "arguments": arguments})


def _problems(call: PlannedToolCall) -> list[str]:
    with pytest.raises(PolicyViolationError) as info:
        check_call(POLICY, CATALOG, call)
    assert info.value.details is not None
    problems = info.value.details["problems"]
    assert isinstance(problems, list)
    return [str(p) for p in problems]


@pytest.mark.parametrize(
    ("call", "risk"),
    [
        (_call("k8s_rollout_status", deployment="api", region="standby"), RiskClass.READ),
        (_call("k8s_rollout_restart", deployment="api", region="standby"), RiskClass.WRITE),
        (_call("db_promote_replica", cluster="pg"), RiskClass.DESTRUCTIVE),
    ],
)
def test_allowed_calls_return_their_risk(call: PlannedToolCall, risk: RiskClass) -> None:
    assert check_call(POLICY, CATALOG, call) is risk


def test_unlisted_tool_is_refused_even_if_offered() -> None:
    catalog = index_catalog([*drsim_catalog(), ToolSpec(server="drsim", name="drop_everything")])
    with pytest.raises(PolicyViolationError, match="not allow-listed"):
        check_call(POLICY, catalog, _call("drop_everything"))


def test_unknown_server_is_refused() -> None:
    call = PlannedToolCall(server="prod", tool="smoke_run", arguments={})
    assert _problems(call) == ["tool is not allow-listed in the execution policy"]


def test_listed_tool_the_server_does_not_offer_is_refused() -> None:
    catalog = index_catalog([s for s in drsim_catalog() if s.name != "cache_ping"])
    with pytest.raises(PolicyViolationError, match="not offered by the server"):
        check_call(POLICY, catalog, _call("cache_ping", cache="c"))


def test_arguments_are_checked_against_the_input_schema() -> None:
    problems = _problems(_call("k8s_rollout_restart", deployment="", region="mars", extra=1))
    assert any("Additional properties" in p for p in problems)
    assert any(p.startswith("arguments: deployment:") for p in problems)
    assert any(p.startswith("arguments: region:") for p in problems)


def test_missing_required_argument() -> None:
    assert any(
        "'cluster' is a required property" in p for p in _problems(_call("db_promote_replica"))
    )


def test_policy_constraints_apply_on_top_of_the_schema() -> None:
    policy = parse_policy(
        json.dumps(
            {
                "servers": {
                    "drsim": {
                        "tools": {
                            "dns_switch_region": {
                                "risk": "destructive",
                                "constraints": {"region": {"const": "standby"}},
                            },
                            "cache_ping": {
                                "risk": "read",
                                "constraints": {"timeout": {"type": "integer"}},
                            },
                        }
                    }
                }
            }
        )
    )
    with pytest.raises(PolicyViolationError) as info:
        check_call(policy, CATALOG, _call("dns_switch_region", service="s", region="primary"))
    assert info.value.details == {
        "tool": "drsim/dns_switch_region",
        "problems": ["region: 'standby' was expected"],
    }
    with pytest.raises(PolicyViolationError, match="required by the policy constraint"):
        check_call(policy, CATALOG, _call("cache_ping", cache="c"))


def test_invalid_server_schema_is_reported() -> None:
    catalog = index_catalog([ToolSpec(server="drsim", name="cache_ping", input_schema={"type": 5})])
    with pytest.raises(PolicyViolationError, match="input schema for this tool is invalid"):
        check_call(POLICY, catalog, _call("cache_ping", cache="c"))


@pytest.mark.parametrize(
    ("policy_risk", "read_only", "destructive", "expected"),
    [
        (RiskClass.READ, True, False, RiskClass.READ),
        (RiskClass.READ, False, None, RiskClass.WRITE),
        (RiskClass.WRITE, None, True, RiskClass.DESTRUCTIVE),
        (RiskClass.DESTRUCTIVE, True, False, RiskClass.DESTRUCTIVE),  # hints never lower
        (RiskClass.WRITE, None, None, RiskClass.WRITE),
    ],
)
def test_server_hints_only_raise_the_risk(
    policy_risk: RiskClass, read_only: bool | None, destructive: bool | None, expected: RiskClass
) -> None:
    spec = ToolSpec(server="s", name="t", read_only_hint=read_only, destructive_hint=destructive)
    assert effective_risk(policy_risk, spec) is expected


def test_verify_calls_must_be_read_only() -> None:
    read = _call("cache_ping", cache="c")
    assert check_verify_call(POLICY, CATALOG, read) is RiskClass.READ
    with pytest.raises(PolicyViolationError, match="verify calls must be read-only"):
        check_verify_call(
            POLICY, CATALOG, _call("cache_warm_from_snapshot", cache="c", snapshot="s")
        )


def test_required_approvals() -> None:
    assert REQUIRED_APPROVALS == {RiskClass.READ: 1, RiskClass.WRITE: 1, RiskClass.DESTRUCTIVE: 2}


@pytest.mark.parametrize(
    "name", ["run_shell", "bash", "exec", "k8s.exec", "Run-Command", "eval_js"]
)
def test_shell_like_tool_names_are_detected(name: str) -> None:
    assert looks_like_shell(name)


@pytest.mark.parametrize("name", ["smoke_run", "db_promote_replica", "k8s_rollout_status"])
def test_normal_tool_names_are_not_shell_like(name: str) -> None:
    assert not looks_like_shell(name)


def test_policy_file_refuses_shell_tools() -> None:
    doc = {"servers": {"drsim": {"tools": {"run_shell": {"risk": "destructive"}}}}}
    with pytest.raises(ConfigError, match="is invalid") as info:
        parse_policy(json.dumps(doc))
    assert "shell-like tools are never allowed: run_shell" in str(info.value.details)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("{not json", "not valid JSON"),
        ('{"servers": {"drsim": {"tools": {"x": {"risk": "scary"}}}}}', "is invalid"),
        (
            '{"servers": {"drsim": {"tools": {"x": '
            '{"risk": "read", "constraints": {"a": {"type": 3}}}}}}}',
            "is invalid",
        ),
        ('{"servers": {}, "extra": 1}', "is invalid"),
    ],
)
def test_bad_policy_documents_fail_fast(text: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        parse_policy(text)


def test_load_policy_from_file(tmp_path: Path) -> None:
    path = tmp_path / "execution-policy.json"
    path.write_text(json.dumps(drsim_policy_dict()), encoding="utf-8")
    policy = load_policy(path)
    assert policy.tool("drsim", "smoke_run") is not None
    assert policy.tool("drsim", "nope") is None
    assert policy.tool("other", "smoke_run") is None


def test_load_policy_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot be read"):
        load_policy(tmp_path / "missing.json")
