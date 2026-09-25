---
name: llm-structured-output
description: Patterns for getting reliable structured JSON reports from small open-source LLMs via Ollama. Use when working on llm/, prompts, or analyzer.py.
---

# Reliable structured output with local models

## Split the work
- Code computes: total minutes, buffer, feasibility, bottleneck steps, dependency health table, risk level from score, execution phases from `dependsOn`.
- LLM produces: `dependsOn` inference, single points of failure, gaps, suggestions, executive summary, and a risk score proposal.
- Merge into `DRReadinessReport`, then validate. Clamp the score to 0-100 and derive `riskLevel` in code.

## Calling the model
- Use Ollama structured outputs: pass the Pydantic `model_json_schema()` of the LLM-owned sub-schema as `format`. Temperature 0 to 0.2, fixed seed for tests and demos.
- Keep the sub-schema small. Several small calls (one per section) beat one huge call for 7-14B models.
- Prompt layout: system role, task, rules, then untrusted data inside explicit delimiters (`<runbook>...</runbook>`), then output spec.
- Include one short few-shot example per section, using values that will not be copied into real output.

## Failure handling
1. Parse JSON. On decode error, retry once with "return only valid JSON".
2. Validate with Pydantic. On error, retry once with the validation messages appended.
3. Transport errors: 3 retries, exponential backoff with jitter.
4. Still failing: return parser and validator results plus `aiAnalysis: unavailable` note and a rule-based fallback score.

## Prompt-injection stance
Runbook text may contain instructions. The system prompt states that delimited content is data only. Output is accepted only through schema validation, and no tool or network access is given to the model.

## Provider abstraction
`LLMProvider.generate(prompt, schema) -> dict` behind a Protocol. Ship `OllamaProvider` and `FakeProvider` (tests). `OpenAICompatibleProvider` covers any `/chat/completions` API (OpenAI, Mistral, vLLM, llama.cpp) through `LLM_PROVIDER=openai_compatible`, with `response_format` `json_schema` or `json_object`.
