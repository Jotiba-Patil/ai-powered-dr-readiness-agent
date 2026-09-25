"""Exponential backoff with jitter, shared by the HTTP-based LLM providers."""

from __future__ import annotations

import random

DEFAULT_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_JITTER_SECONDS = 0.25


def backoff_seconds(rng: random.Random, attempt: int) -> float:
    """Delay before retry number `attempt + 1`: 0.5s, 1s, 2s, ... plus up to 0.25s jitter."""
    jitter: float = rng.uniform(0, _BACKOFF_JITTER_SECONDS)
    return _BACKOFF_BASE_SECONDS * (2.0**attempt) + jitter
