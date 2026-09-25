"""LLMProvider: the injectable interface for calling a structured-output model."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    """Calls a model with a system/user prompt and a JSON schema for its reply.

    Returns the raw response text (expected to be JSON matching `schema`, but not
    guaranteed to be -- callers validate it). Raises `AnalysisError` only after
    exhausting transport-level retries; a malformed-but-received response is
    returned as-is so the caller can drive its own correction retry.
    """

    async def generate(
        self, *, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> str: ...
