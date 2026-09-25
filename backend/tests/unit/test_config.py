from pathlib import Path

import pytest

from dr_agent.config import Settings, load_settings
from dr_agent.utils.errors import ConfigError

ENV_VARS = [
    "PORT",
    "LOG_LEVEL",
    "HEALTH_CHECK_TIMEOUT_MS",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_RESPONSE_FORMAT",
    "LLM_MAX_TOKENS",
    "LLM_TIMEOUT_SECONDS",
    "HEALTH_CHECKER",
    "HEALTH_CHECK_CHAOS",
    "API_HOST",
    "API_ALLOWED_DIR",
    "API_MAX_UPLOAD_BYTES",
    "API_WAIT_TIMEOUT_SECONDS",
    "API_MAX_CONCURRENT_JOBS",
    "API_MAX_STORED_JOBS",
    "CORS_ORIGINS",
    "EXECUTION_ENABLED",
    "EXECUTION_ALLOW_LIVE",
    "EXECUTION_DB_PATH",
    "DB_PATH",
    "HISTORY_ENABLED",
    "HISTORY_RETENTION_DAYS",
    "HISTORY_STALE_AFTER_HOURS",
    "KNOWLEDGE_ENABLED",
    "KNOWLEDGE_MAX_RUNS",
    "KNOWLEDGE_MAX_ANALYSES",
    "KNOWLEDGE_IN_PROMPT",
    "MCP_SERVERS_FILE",
    "EXECUTION_POLICY_FILE",
    "EXECUTION_APPROVAL_TIMEOUT_MINUTES",
    "EXECUTION_TOOL_TIMEOUT_SECONDS",
    "EXECUTION_MAX_TOOL_CALLS",
    "EXECUTION_MAX_ACTIVE",
    "EXECUTION_AI_PROPOSALS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    s = load_settings(env_file=None)
    assert s.port == 8000
    assert s.log_level == "info"
    assert s.health_check_timeout_ms == 3000
    assert s.llm_provider == "ollama"
    assert s.llm_model == "qwen2.5:7b-instruct"
    assert s.llm_base_url == "http://localhost:11434"
    assert s.llm_max_tokens == 2048
    assert s.llm_api_key is None
    assert s.llm_response_format == "json_schema"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9001")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:3b-instruct")
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/")
    s = load_settings(env_file=None)
    assert s.port == 9001
    assert s.log_level == "debug"
    assert s.llm_model == "qwen2.5:3b-instruct"
    assert s.llm_base_url == "http://ollama:11434"


def test_env_file_is_read(tmp_path: Path) -> None:
    env = tmp_path / "test.env"
    env.write_text("PORT=7777\n")
    assert load_settings(env_file=str(env)).port == 7777


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PORT", "0"),
        ("PORT", "70000"),
        ("PORT", "abc"),
        ("LOG_LEVEL", "loud"),
        ("HEALTH_CHECK_TIMEOUT_MS", "-5"),
        ("LLM_PROVIDER", "openai"),
        ("LLM_MODEL", ""),
        ("LLM_BASE_URL", "not-a-url"),
        ("LLM_BASE_URL", "ftp://host"),
        ("LLM_MAX_TOKENS", "0"),
    ],
)
def test_invalid_values_fail_fast(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert name in info.value.message
    assert info.value.code == "CONFIG_ERROR"


def test_settings_are_frozen() -> None:
    s = Settings(_env_file=None)
    with pytest.raises(ValueError, match="frozen"):
        s.port = 1  # type: ignore[misc]  # asserting immutability


def test_phase5_defaults() -> None:
    s = load_settings(env_file=None)
    assert s.health_checker == "mock"
    assert s.health_check_chaos is False
    assert s.llm_timeout_seconds == 300.0
    assert s.api_host == "127.0.0.1"
    assert s.api_allowed_dir == "mock-data"
    assert s.api_max_upload_bytes == 1_048_576
    assert s.api_max_concurrent_jobs == 1
    assert s.cors_origin_list == ["http://localhost:5173"]


def test_cors_origins_are_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " http://a.test , ,http://b.test ")
    assert load_settings(env_file=None).cors_origin_list == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_PROVIDER", "openai"),
        ("HEALTH_CHECKER", "ping"),
        ("API_MAX_UPLOAD_BYTES", "0"),
        ("API_MAX_CONCURRENT_JOBS", "0"),
    ],
)
def test_invalid_phase5_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert info.value.details is not None
    assert name in info.value.details


def test_openai_compatible_provider_reads_key_and_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1/")
    monkeypatch.setenv("LLM_API_KEY", "  fake-key  ")
    monkeypatch.setenv("LLM_RESPONSE_FORMAT", "json_object")
    s = load_settings(env_file=None)
    assert s.llm_provider == "openai_compatible"
    assert s.llm_base_url == "https://api.openai.com/v1"
    assert s.llm_api_key is not None
    assert s.llm_api_key.get_secret_value() == "fake-key"
    assert s.llm_response_format == "json_object"
    assert "fake-key" not in repr(s)


@pytest.mark.parametrize("key", [None, "", "   "])
def test_openai_compatible_requires_an_api_key(
    monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    if key is not None:
        monkeypatch.setenv("LLM_API_KEY", key)
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert info.value.details is not None
    assert "LLM_API_KEY" in info.value.details


def test_blank_api_key_is_ignored_for_other_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", " ")
    assert load_settings(env_file=None).llm_api_key is None


def test_invalid_response_format_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_RESPONSE_FORMAT", "yaml")
    with pytest.raises(ConfigError, match="LLM_RESPONSE_FORMAT"):
        load_settings(env_file=None)
