"""`MCP_SERVERS_FILE`: the only place MCP servers are defined (ADR 0006, control 3).

`{"<key>": {"transport": "stdio", "command", "args", "env", "cwd"}
          | {"transport": "http", "url", "headers"}}`

`${VAR}` references anywhere in the file are resolved from the environment,
so credentials stay out of the file. Environment values and headers are held
as `SecretStr`, so they never show up in a repr, a log line or an error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, JsonValue, SecretStr, TypeAdapter, field_validator
from pydantic import ValidationError as PydanticValidationError

from dr_agent.models.base import CamelModel
from dr_agent.utils.errors import ConfigError

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class StdioServerConfig(CamelModel):
    transport: Literal["stdio"]
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, SecretStr] = Field(default_factory=dict)
    cwd: str | None = None


class HttpServerConfig(CamelModel):
    transport: Literal["http"]
    url: str
    headers: dict[str, SecretStr] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an http(s) URL")
        return value


ServerConfig = Annotated[StdioServerConfig | HttpServerConfig, Field(discriminator="transport")]
_SERVERS = TypeAdapter(dict[str, ServerConfig])


def parse_servers(
    text: str, environ: Mapping[str, str], *, source: str = "MCP servers file"
) -> dict[str, StdioServerConfig | HttpServerConfig]:
    try:
        raw: JsonValue = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{source} is not valid JSON", details={"reason": exc.msg}) from exc
    missing: set[str] = set()
    resolved = _resolve(raw, environ, missing)
    if missing:
        raise ConfigError(
            f"{source} references unset environment variables",
            details={"variables": sorted(missing)},
        )
    try:
        servers = _SERVERS.validate_python(resolved)
    except PydanticValidationError as exc:
        raise ConfigError(
            f"{source} is invalid",
            details={"errors": exc.errors(include_url=False, include_input=False)},
        ) from exc
    bad_keys = sorted(key for key in servers if not _KEY_RE.match(key))
    if bad_keys:
        raise ConfigError(
            f"{source}: server keys must be 1-64 letters, digits, '-' or '_'",
            details={"keys": bad_keys},
        )
    return servers


def load_servers(
    path: Path, environ: Mapping[str, str]
) -> dict[str, StdioServerConfig | HttpServerConfig]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("MCP servers file cannot be read", details={"path": str(path)}) from exc
    return parse_servers(text, environ, source=f"MCP servers file {path.name}")


def _resolve(value: JsonValue, environ: Mapping[str, str], missing: set[str]) -> JsonValue:
    if isinstance(value, str):

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in environ:
                missing.add(name)
                return ""
            return environ[name]

        return _VAR_RE.sub(substitute, value)
    if isinstance(value, list):
        return [_resolve(item, environ, missing) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, environ, missing) for key, item in value.items()}
    return value
