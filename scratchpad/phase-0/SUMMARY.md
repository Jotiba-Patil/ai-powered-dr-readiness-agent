# Phase 0 Summary: Decisions and LLM Spike

Date: 2026-09-21. Status: **Done**.

## Outcome
The local-LLM approach is viable. Both tested models returned schema-valid JSON in every run when given a JSON schema through Ollama. Quality is the weak point, which confirms the plan's split between deterministic checks in code and LLM reasoning.

## Environment found
| Item | Value |
|---|---|
| OS | Windows 11 Home |
| CPU / RAM | Intel i7-1360P, 15.7 GB |
| GPU | Intel Iris Xe only (no CUDA), so CPU inference |
| Python | 3.14.6 installed, 3.12.14 available through uv |
| Node | 26.1.0 |
| uv, git | installed |
| Docker | **not installed** |
| make | **not installed** |
| Ollama | not installed at start; **installed 0.34.2 via winget** during this phase |

## Spike setup
- Script: `spike_structured_output.py` (throwaway, stdlib + pydantic, run under Python 3.12).
- Input: a small payment-gateway runbook with deliberate flaws (owners "team", vague step 1, no validation, no rollback, 30 min RTO for 45 min of work) and an inventory with Kafka DOWN and one dependency not in inventory.
- Request: the LLM-owned part of the report only (step dependencies, SPOFs, gaps, suggestions, proposed risk score, summary), sent as a JSON schema in Ollama's `format` field. Temperature 0.1, seed 42, 4096 context.
- Raw results: `results/qwen2.5_7b-instruct.json` and `results/qwen2.5_3b-instruct.json`. Two runs each.

## Results
| Metric | qwen2.5:7b-instruct | qwen2.5:3b-instruct |
|---|---|---|
| Schema-valid output | 2 of 2 | 2 of 2 |
| Wall time per call | 131 to 143 s | 80 to 88 s |
| Generation speed | 5.0 to 5.3 tokens/s | 10.9 tokens/s |
| Output tokens | about 620 to 640 | about 790 to 840 |
| Model load time (first call) | about 16 s | about 8 s |
| Proposed risk score | 75 and 75 | 60 and 60 |
| Gap types found | MISSING_STEP, UNVERIFIED_DEPENDENCY / MISSING_ROLLBACK, MISSING_STEP | MISSING_STEP only |
| Flagged the "team" owners (OWNER_AMBIGUITY) | no | no |
| Flagged missing validation (NO_VALIDATION) | no | no |
| Single points of failure listed | 1 | 3 |

## Findings
1. **Structured output works.** Constrained JSON meant no retries were needed in 4 of 4 runs. The correction-retry path is still required for robustness.
2. **Quality is inconsistent and shallow.** Neither model noticed the obvious "team" owners or the total absence of validation steps. The 7B result changed between runs even with a fixed seed and low temperature (different gap types). The step dependency output was a plain chain with no real inference.
3. **Latency is high on CPU.** One 7B call takes over two minutes. Splitting into several section calls would add up to several minutes per report.
4. **The 3B model is faster but clearly weaker.** It suits development and tests, not the default.

## Decisions
| # | Decision | Reason |
|---|---|---|
| D1 | Default model `qwen2.5:7b-instruct`; `qwen2.5:3b-instruct` documented as a fast dev option | Better gap coverage; 3B found almost nothing |
| D2 | Deterministic gap detection in code for `OWNER_AMBIGUITY`, `NO_VALIDATION`, `MISSING_ROLLBACK`, `UNVERIFIED_DEPENDENCY`, plus RTO math, dependency health and execution phases. LLM adds SPOFs, vague-instruction and missing-step findings, suggestions and the summary | The spike showed the LLM misses rule-checkable issues |
| D3 | Analysis runs as an asynchronous job in the API: `POST` returns a job id, client polls for the result. CLI shows a spinner. UI shows progress | A single request can exceed typical proxy and browser timeouts |
| D4 | Order the analysis so rule-based results are returned first and marked as final, then AI sections are merged in | Gives immediate value and a natural graceful-degradation path |
| D5 | Pin Python 3.12 through uv (`requires-python` and `.python-version`) | Available already; avoids 3.14 dependency risk |
| D6 | Use `poethepoet` tasks (`uv run poe test`) instead of a Makefile | `make` is not installed on this Windows machine and is not a standard Windows tool |
| D7 | Keep Docker Compose in Phase 7 as an authored but unverified deliverable unless Docker is installed | Docker is not installed here |
| D8 | Keep the CLI, single-analysis dashboard without persistence, and table support for steps | These were the plan defaults and were not changed |
| D9 | Run the model with `keep_alive` set so it stays loaded between calls | Avoids the roughly 16 s reload per call |

## Impact on the plan
- Phase 1: add `poethepoet` tasks instead of a Makefile, and pin Python 3.12.
- Phase 4: implement the rule-based gap detector as a first-class module with its own tests, and treat LLM output as additive. Add a few-shot example and explicit checklists to the prompt to try to improve recall, then re-measure.
- Phase 5: job-based API with polling.
- Phase 7: Docker steps are untested locally.

## Open items to confirm with the user (defaults applied)
- Whether Claude may be added later as an optional provider. Not implemented; the provider interface keeps the option open.
- Whether stored history and trends are wanted. Deferred.
- Installing Docker if a verified Compose setup is required.

## Artifacts
- `spike_structured_output.py`
- `results/qwen2.5_7b-instruct.json`, `results/qwen2.5_3b-instruct.json`
