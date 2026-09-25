"""Runbook-execution settings (Phase 9): off by default, validated, mapped to limits."""

from datetime import timedelta

import pytest
from test_config import ENV_VARS

from dr_agent.config import load_settings
from dr_agent.execution.session import ExecutionLimits
from dr_agent.utils.errors import ConfigError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_execution_is_off_by_default() -> None:
    s = load_settings(env_file=None)
    assert s.execution_enabled is False
    assert s.execution_allow_live is False
    assert (s.mcp_servers_file, s.execution_policy_file) == (
        "mcp-servers.json",
        "execution-policy.json",
    )
    assert s.execution_approval_timeout_minutes == 30.0
    assert s.execution_tool_timeout_seconds == 120.0
    assert (s.execution_max_tool_calls, s.execution_max_active) == (50, 3)
    assert s.execution_ai_proposals is True


def test_execution_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("EXECUTION_ALLOW_LIVE", "true")
    monkeypatch.setenv("EXECUTION_MAX_TOOL_CALLS", "5")
    s = load_settings(env_file=None)
    assert (s.execution_enabled, s.execution_allow_live, s.execution_max_tool_calls) == (
        True,
        True,
        5,
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EXECUTION_ENABLED", "maybe"),
        ("EXECUTION_APPROVAL_TIMEOUT_MINUTES", "0"),
        ("EXECUTION_TOOL_TIMEOUT_SECONDS", "-1"),
        ("EXECUTION_MAX_TOOL_CALLS", "0"),
        ("EXECUTION_MAX_ACTIVE", "0"),
        ("EXECUTION_DB_PATH", ""),
    ],
)
def test_invalid_execution_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert info.value.details is not None
    assert name in info.value.details


def test_execution_limits_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("EXECUTION_APPROVAL_TIMEOUT_MINUTES", "5")
    limits = ExecutionLimits.from_settings(load_settings(env_file=None))
    assert limits == ExecutionLimits(
        enabled=True,
        allow_live=False,
        approval_timeout=timedelta(minutes=5),
        tool_timeout_seconds=120.0,
        max_tool_calls=50,
        max_active=3,
    )
    monkeypatch.delenv("EXECUTION_ENABLED")
    monkeypatch.delenv("EXECUTION_APPROVAL_TIMEOUT_MINUTES")
    assert ExecutionLimits() == ExecutionLimits.from_settings(load_settings(env_file=None))
