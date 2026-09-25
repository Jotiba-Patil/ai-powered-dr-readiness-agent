"""MCP_SERVERS_FILE: both transports, ${VAR} resolution, secrets kept secret, bad files."""

import json
from pathlib import Path

import pytest

from dr_agent.tools.servers_config import (
    HttpServerConfig,
    StdioServerConfig,
    load_servers,
    parse_servers,
)
from dr_agent.utils.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_both_transports_and_variables() -> None:
    doc = {
        "local": {"transport": "stdio", "command": "${PY}", "args": ["-m", "x"], "env": {"K": "v"}},
        "remote": {
            "transport": "http",
            "url": "https://${HOST}/mcp",
            "headers": {"Authorization": "Bearer ${TOKEN}"},
        },
    }
    servers = parse_servers(
        json.dumps(doc), {"PY": "python", "HOST": "mcp.internal", "TOKEN": "s3cr3t"}
    )
    local, remote = servers["local"], servers["remote"]
    assert isinstance(local, StdioServerConfig)
    assert local.command == "python"
    assert isinstance(remote, HttpServerConfig)
    assert remote.url == "https://mcp.internal/mcp"
    assert remote.headers["Authorization"].get_secret_value() == "Bearer s3cr3t"
    assert "s3cr3t" not in repr(servers)


def test_unset_variables_are_named_but_not_guessed() -> None:
    doc = {"r": {"transport": "http", "url": "https://${HOST}/mcp", "headers": {"A": "${TOK}"}}}
    with pytest.raises(ConfigError, match="unset environment variables") as info:
        parse_servers(json.dumps(doc), {})
    assert info.value.details == {"variables": ["HOST", "TOK"]}


@pytest.mark.parametrize(
    ("doc", "match"),
    [
        ("{bad", "not valid JSON"),
        ('{"a": {"transport": "ssh", "command": "x"}}', "is invalid"),
        ('{"a": {"transport": "http", "url": "ftp://x"}}', "is invalid"),
        ('{"a": {"transport": "stdio", "command": ""}}', "is invalid"),
        ('{"a": {"transport": "stdio", "command": "x", "shell": true}}', "is invalid"),
        ('{"bad key": {"transport": "stdio", "command": "x"}}', "server keys must be"),
    ],
)
def test_bad_documents_fail_fast(doc: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        parse_servers(doc, {})


def test_invalid_values_are_not_echoed() -> None:
    doc = {"a": {"transport": "http", "url": "not a url ${T}"}}
    with pytest.raises(ConfigError) as info:
        parse_servers(json.dumps(doc), {"T": "s3cr3t"})
    assert "s3cr3t" not in str(info.value.details)


def test_load_servers(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot be read"):
        load_servers(tmp_path / "missing.json", {})
    default = load_servers(REPO_ROOT / "mcp-servers.json", {})
    assert list(default) == ["drsim"]
    drsim = default["drsim"]
    assert isinstance(drsim, StdioServerConfig)
    assert drsim.args == ["-m", "dr_agent.mock_mcp"]
