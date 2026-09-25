"""Step identity across runbook versions (design analysis-history section 9.2).

A step is the same step when its normalized action text and target system are
the same. Rewording a step starts a new history: exact matching never merges
two different steps (fuzzy matching is later work).
"""

from __future__ import annotations

import re

from dr_agent.execution.canonical import sha256_hex

_SPACE = re.compile(r"\s+")


def step_fingerprint(action: str, target_system: str | None) -> str:
    normalized = _SPACE.sub(" ", action).strip().lower()
    target = (target_system or "").strip().lower()
    return sha256_hex(f"{normalized}\x1f{target}")
