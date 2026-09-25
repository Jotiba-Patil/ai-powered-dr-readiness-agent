"""Environment-based configuration, validated at startup (fail fast)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dr_agent.utils.errors import ConfigError

DEFAULT_DB_FILE = "dr-agent.db"

LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class Settings(BaseSettings):
    """Runtime settings. Field names map to upper-case env vars (PORT, LOG_LEVEL, ...)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "info"
    health_check_timeout_ms: int = Field(default=3000, gt=0)
    health_checker: Literal["mock", "live"] = "mock"
    health_check_chaos: bool = False
    # ollama: Ollama's native API. openai_compatible: any /chat/completions API
    # (OpenAI, Mistral, vLLM, ...) with LLM_BASE_URL set to its root, e.g. .../v1.
    llm_provider: Literal["ollama", "openai_compatible", "none"] = "ollama"
    llm_model: str = Field(default="qwen2.5:7b-instruct", min_length=1)
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: SecretStr | None = Field(default=None, validate_default=True)
    # json_object for servers without JSON-schema structured output.
    llm_response_format: Literal["json_schema", "json_object"] = "json_schema"
    llm_max_tokens: int = Field(default=2048, gt=0)
    llm_timeout_seconds: float = Field(default=300.0, gt=0)
    # API (Phase 5)
    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_allowed_dir: str = Field(default="mock-data", min_length=1)
    api_max_upload_bytes: int = Field(default=1_048_576, gt=0)
    api_wait_timeout_seconds: float = Field(default=30.0, gt=0)
    api_max_concurrent_jobs: int = Field(default=1, ge=1)
    api_max_stored_jobs: int = Field(default=100, ge=1)
    cors_origins: str = "http://localhost:5173"
    # Runbook execution (Phase 9+). Off by default; live mode is a second opt-in.
    execution_enabled: bool = False
    execution_allow_live: bool = False
    mcp_servers_file: str = Field(default="mcp-servers.json", min_length=1)
    execution_policy_file: str = Field(default="execution-policy.json", min_length=1)
    execution_approval_timeout_minutes: float = Field(default=30.0, gt=0)
    execution_tool_timeout_seconds: float = Field(default=120.0, gt=0)
    execution_max_tool_calls: int = Field(default=50, ge=1)
    execution_max_active: int = Field(default=3, ge=1)
    # Ask the LLM for a call for steps without a Tool: annotation (one model call per step).
    execution_ai_proposals: bool = True
    # One SQLite file for analyses and executions (ADR 0007). EXECUTION_DB_PATH is
    # the older name and is still read when DB_PATH is not set.
    db_path: str | None = Field(default=None, min_length=1)
    execution_db_path: str | None = Field(default=None, min_length=1)
    history_enabled: bool = True
    history_retention_days: int = Field(default=0, ge=0, description="0 keeps forever")
    history_stale_after_hours: float = Field(default=24.0, gt=0)
    # Knowledge base (Phase 14, ADR 0009): measured facts from history, needs history on.
    knowledge_enabled: bool = True
    knowledge_max_runs: int = Field(default=10, ge=1, le=100)
    knowledge_max_analyses: int = Field(default=20, ge=1, le=200)
    knowledge_in_prompt: bool = True

    @property
    def database_path(self) -> Path:
        return Path(self.db_path or self.execution_db_path or DEFAULT_DB_FILE)

    @property
    def cors_origin_list(self) -> list[str]:
        """`CORS_ORIGINS` is a comma-separated list (easier to set in env than JSON)."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_level(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("llm_api_key")
    @classmethod
    def _require_api_key(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        key = value.get_secret_value().strip() if value else ""
        if not key and info.data.get("llm_provider") == "openai_compatible":
            raise ValueError("is required when LLM_PROVIDER=openai_compatible")
        return SecretStr(key) if key else None

    @field_validator("llm_base_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an http(s) URL such as http://localhost:11434")
        return value.rstrip("/")


def load_settings(*, env_file: str | None = ".env") -> Settings:
    """Build settings from the environment, raising `ConfigError` with all problems listed."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        problems = {
            ".".join(str(part) for part in err["loc"]).upper(): err["msg"] for err in exc.errors()
        }
        raise ConfigError(
            "Invalid configuration: " + "; ".join(f"{k}: {v}" for k, v in problems.items()),
            details=dict(problems),
        ) from exc
