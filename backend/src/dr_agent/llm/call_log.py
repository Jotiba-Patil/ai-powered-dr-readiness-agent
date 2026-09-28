"""One structured log line per LLM HTTP attempt, shared by the HTTP providers.

Only metadata is logged (provider, model, endpoint, attempt, status, timing,
sizes, token usage). Prompt and response text are never logged: they carry
untrusted runbook content and model output.
"""

from __future__ import annotations

from dataclasses import dataclass

from dr_agent.utils.logging import get_logger, scrub_url_credentials

_log = get_logger("dr_agent.llm")


@dataclass(frozen=True)
class CallTarget:
    provider: str
    model: str
    url: str


def log_attempt(
    target: CallTarget,
    *,
    attempt: int,
    max_attempts: int,
    duration_ms: float,
    outcome: str,
    status: int | None = None,
    prompt_chars: int | None = None,
    response_chars: int | None = None,
    usage: dict[str, int] | None = None,
    reason: str | None = None,
) -> None:
    """Log one attempt. `outcome` is `ok`, `retry` or `failed`; failures log at warning."""
    fields: dict[str, object] = {
        "provider": target.provider,
        "model": target.model,
        "url": scrub_url_credentials(target.url),
        "attempt": attempt + 1,
        "max_attempts": max_attempts,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 1),
    }
    optional: dict[str, object | None] = {
        "status": status,
        "prompt_chars": prompt_chars,
        "response_chars": response_chars,
        "reason": reason,
    }
    fields.update({key: value for key, value in optional.items() if value is not None})
    if usage:
        fields.update(usage)
    if outcome == "ok":
        _log.info("llm_call", **fields)
    else:
        _log.warning("llm_call", **fields)


def usage_from(body: object) -> dict[str, int]:
    """Token counts from an OpenAI-style `usage` or Ollama `*_eval_count` body, if present."""
    if not isinstance(body, dict):
        return {}
    usage = body.get("usage")
    source = usage if isinstance(usage, dict) else body
    names = {
        "prompt_tokens": ("prompt_tokens", "prompt_eval_count"),
        "completion_tokens": ("completion_tokens", "eval_count"),
        "total_tokens": ("total_tokens",),
    }
    found: dict[str, int] = {}
    for name, keys in names.items():
        for key in keys:
            value = source.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                found[name] = value
                break
    return found
