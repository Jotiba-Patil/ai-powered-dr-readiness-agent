"""Decode and validate an LLM response into a Pydantic model, with one retry each.

Two things can go wrong with a small model's reply: it is not valid JSON, or it
is JSON that fails the Pydantic schema. Each gets exactly one retry with an
amended prompt -- "JSON only" for a decode failure, the concrete validation
errors for a schema failure -- per `llm-structured-output`. Transport failures
are the provider's problem (already retried there) and propagate as
`AnalysisError` straight out of this function. `get_validated()` serves any
response schema (the analysis, execution tool proposals); `get_llm_analysis()`
is the analysis-specific shorthand.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from dr_agent.llm.base import LLMProvider
from dr_agent.llm.schemas import LlmAnalysis
from dr_agent.utils.errors import AnalysisError

_DECODE_RETRY_NOTE = (
    "\n\nYour previous reply was not valid JSON. Reply with only a single valid "
    "JSON object, no other text."
)


async def get_llm_analysis(
    provider: LLMProvider, *, system_prompt: str, user_prompt: str
) -> LlmAnalysis:
    return await get_validated(
        provider, LlmAnalysis, system_prompt=system_prompt, user_prompt=user_prompt
    )


async def get_validated[M: BaseModel](
    provider: LLMProvider, model: type[M], *, system_prompt: str, user_prompt: str
) -> M:
    schema = model.model_json_schema()
    raw = await provider.generate(
        system_prompt=system_prompt, user_prompt=user_prompt, schema=schema
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raw = await provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt + _DECODE_RETRY_NOTE,
            schema=schema,
        )
        return await _validate_or_retry(provider, model, schema, system_prompt, user_prompt, raw)

    return await _validate_or_retry(provider, model, schema, system_prompt, user_prompt, raw, data)


async def _validate_or_retry[M: BaseModel](
    provider: LLMProvider,
    model: type[M],
    schema: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    raw: str,
    data: object | None = None,
) -> M:
    if data is None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AnalysisError(
                "LLM response was not valid JSON even after a correction retry",
                details={"lastResponse": raw[:2000]},
            ) from exc

    try:
        return model.model_validate(data)
    except PydanticValidationError as first_error:
        retry_prompt = user_prompt + _validation_retry_note(first_error)
        raw = await provider.generate(
            system_prompt=system_prompt, user_prompt=retry_prompt, schema=schema
        )
        try:
            return model.model_validate(json.loads(raw))
        except (json.JSONDecodeError, PydanticValidationError) as second_error:
            raise AnalysisError(
                "LLM response failed schema validation after a correction retry",
                details={"errors": str(second_error), "lastResponse": raw[:2000]},
            ) from second_error


def _validation_retry_note(error: PydanticValidationError) -> str:
    messages = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()
    )
    return f"\n\nYour previous reply failed validation: {messages}. Reply with corrected JSON only."
