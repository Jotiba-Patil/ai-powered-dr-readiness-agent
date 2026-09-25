"""History settings (Phase 13): on by default, one database file, older name still read."""

from pathlib import Path

import pytest
from test_config import ENV_VARS

from dr_agent.config import DEFAULT_DB_FILE, load_settings
from dr_agent.utils.errors import ConfigError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_history_defaults() -> None:
    s = load_settings(env_file=None)
    assert s.history_enabled is True
    assert (s.history_retention_days, s.history_stale_after_hours) == (0, 24.0)
    assert s.database_path == Path(DEFAULT_DB_FILE)
    assert (s.knowledge_enabled, s.knowledge_in_prompt) == (True, True)
    assert (s.knowledge_max_runs, s.knowledge_max_analyses) == (10, 20)


def test_execution_db_path_is_still_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_DB_PATH", "old.db")
    assert load_settings(env_file=None).database_path == Path("old.db")
    monkeypatch.setenv("DB_PATH", "new.db")
    assert load_settings(env_file=None).database_path == Path("new.db")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DB_PATH", ""),
        ("HISTORY_RETENTION_DAYS", "-1"),
        ("HISTORY_STALE_AFTER_HOURS", "0"),
        ("KNOWLEDGE_MAX_RUNS", "0"),
        ("KNOWLEDGE_MAX_ANALYSES", "201"),
    ],
)
def test_invalid_history_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert info.value.details is not None
    assert name in info.value.details
