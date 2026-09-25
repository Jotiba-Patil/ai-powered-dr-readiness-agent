"""AI proposals for unannotated steps (design 4.3, ADR 0002 tier 2).

The model sees only allow-listed tools. Its answer is validated as a
`ToolProposal`, then as a call: an off-list tool, or arguments that fail the
tool's schema or the policy constraints, discard the proposal and the step
becomes manual with the reason recorded. A valid proposal still goes to review
(`PROPOSED`); it is never approvable as-is without a named person accepting it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError as PydanticValidationError

from dr_agent.execution.policy import Catalog, check_call
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.llm.base import LLMProvider
from dr_agent.llm.parse import get_validated
from dr_agent.llm.prompts.execution import SYSTEM_PROMPT, build_proposal_prompt
from dr_agent.llm.proposal_schema import ToolProposal
from dr_agent.models.runbook import PlannedToolCall, Step
from dr_agent.utils.errors import AnalysisError, PolicyViolationError


@dataclass(frozen=True)
class ProposalOutcome:
    """A reviewed-later call, or `call=None` with the reason the step stays manual."""

    call: PlannedToolCall | None
    rationale: str = ""
    confidence: str | None = None
    reason: str | None = None


def _manual(reason: str) -> ProposalOutcome:
    return ProposalOutcome(call=None, reason=reason)


class ToolProposer:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def propose(
        self, step: Step, *, policy: ExecutionPolicy, catalog: Catalog
    ) -> ProposalOutcome:
        allowed = [spec for key, spec in sorted(catalog.items()) if policy.tool(*key) is not None]
        if not allowed:
            return _manual("no allow-listed tools are available")
        try:
            proposal = await get_validated(
                self._llm,
                ToolProposal,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_proposal_prompt(step, allowed),
            )
        except AnalysisError as exc:
            return _manual(f"AI proposal unavailable: {exc.message}")
        if proposal.manual:
            return _manual(f"AI suggests a manual step: {proposal.reason or 'no reason given'}")

        name = f"{proposal.server}/{proposal.tool}"
        if (proposal.server, proposal.tool) not in {(s.server, s.name) for s in allowed}:
            return _manual(f"AI proposal discarded: {name[:200]} is not an allow-listed tool")
        try:
            call = PlannedToolCall.model_validate(
                {
                    "server": proposal.server,
                    "tool": proposal.tool,
                    "arguments": proposal.arguments or {},
                }
            )
            check_call(policy, catalog, call)
        except (PydanticValidationError, PolicyViolationError) as exc:
            detail = exc.message if isinstance(exc, PolicyViolationError) else "invalid call"
            return _manual(f"AI proposal discarded: {detail}")
        return ProposalOutcome(
            call=call, rationale=proposal.rationale, confidence=proposal.confidence
        )


async def propose_missing(
    proposer: ToolProposer | None,
    steps: Iterable[Step],
    *,
    policy: ExecutionPolicy,
    catalog: Catalog,
) -> dict[int, ProposalOutcome]:
    """Proposals for every step without a `Tool:` annotation (one model call each)."""
    if proposer is None:
        return {}
    return {
        step.step_number: await proposer.propose(step, policy=policy, catalog=catalog)
        for step in steps
        if step.tool_call is None
    }
