"""Canonical JSON and SHA-256 helpers for call hashes and the audit chain."""

from __future__ import annotations

import hashlib
import json

from pydantic import JsonValue


def canonical_json(value: object) -> str:
    """Sorted keys, no whitespace, so equal data always hashes the same."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_hash(server: str, tool: str, arguments: dict[str, JsonValue]) -> str:
    """What an approval binds to (ADR 0003): SHA-256 of `{server, tool, arguments}`."""
    return sha256_hex(canonical_json({"server": server, "tool": tool, "arguments": arguments}))
