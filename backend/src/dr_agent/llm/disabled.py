"""DisabledProvider: `LLM_PROVIDER=none` -- rule-based analysis only, no model call.

Useful offline, in CI gates that must not depend on a model server, and for
deterministic demos. It fails immediately with `AnalysisError`, which
`core/analyzer.py` already turns into a graceful rule-based-only report.
"""

from __future__ import annotations

from dr_agent.utils.errors import AnalysisError


class DisabledProvider:
    async def generate(
        self, *, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> str:
        raise AnalysisError("LLM provider is disabled (LLM_PROVIDER=none)")
