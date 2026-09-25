# Phase 4 Summary: LLM Analysis and Report Formatters

Date: 2026-09-22. Status: **Done**.

## Phase 0/1/2/3 validation (done first)
Re-ran the full gate before starting: `uv run poe lint` (ruff check, ruff
format --check, mypy --strict) and `uv run poe test` — both green, 185 tests,
99.09% coverage, matching `scratchpad/phase-3/SUMMARY.md` exactly. Cross-checked
`docs/IMPLEMENTATION_PLAN.md` and `README.md` against the actual repo state;
both already reflected Phase 0-3 as done, no discrepancies found.

## What was built
| Area | Files |
|---|---|
| LLM interface | `llm/base.py`: `LLMProvider` Protocol, `generate(system_prompt, user_prompt, schema) -> str` |
| LLM sub-schema | `llm/schemas.py`: `LlmAnalysis` (`stepDependencies`, `singlePointsOfFailure`, `gapAnalysis`, `suggestions`, `summary`, `riskScore`) — the reasoning-heavy fields only, reusing `Gap`/`SinglePointOfFailure`/`Suggestion` from `models/report.py` |
| Prompts | `llm/prompts/system.py` (senior-SRE role, "never say looks good", untrusted-data stance for `<runbook>`/`<validation>`); `llm/prompts/analysis.py` (embeds the parsed runbook minus `rawMarkdown`, dependency health, RTO analysis and the already-checked rule gaps; an all-placeholder few-shot example) |
| Ollama provider | `llm/ollama.py`: `OllamaProvider`, calls `/api/chat` with `format=<json schema>`, `temperature=0`; 3 retries with exponential backoff + jitter on `httpx.HTTPError`; injected `httpx.AsyncClient`, `random.Random`, sleeper |
| Fake provider | `llm/fake.py`: `FakeProvider`, replays scripted responses or raises a scripted `AnalysisError`, records every call — used by every test, never a real network call |
| Response parsing | `llm/parse.py`: `get_llm_analysis()` — one retry on JSON-decode failure ("JSON only" note), one retry on Pydantic validation failure (the concrete error appended); raises `AnalysisError` if still failing |
| Deterministic rules | `core/rto_analysis.py` (total/buffer/feasible, minimal greedy bottleneck-step set); `core/execution_plan.py` (Kahn's-algorithm phase layering from merged `dependsOn`, cycle-safe); `core/gap_rules.py` (`OWNER_AMBIGUITY`, `NO_VALIDATION`, `MISSING_ROLLBACK`, `UNVERIFIED_DEPENDENCY`); `core/risk_score.py` (rule-based fallback score) |
| Orchestrator | `core/analyzer.py`: `run_analysis(runbook, dependency_health, llm, ...)` — computes rules, calls the LLM, merges `stepDependencies` (filtered to known, non-self step numbers) into the execution plan, drops any rule-owned `GapType` the LLM emits anyway, degrades gracefully to rule-only results plus `aiNote` on `AnalysisError` |
| Formatters | `formatters/format_json.py`, `formatters/format_terminal.py` (Rich, `box.ASCII` tables, color-coded risk score), `formatters/format_html.py` (Jinja2, `select_autoescape`) + `templates/report.html.jinja` — a new top-level package, **not** under `core/` (see P4-4) |
| Tests | 12 new test files, 56 new tests (241 total), 98.84% coverage; golden end-to-end report `mock-data/expected-reports/estimate-service.json`; formatter snapshots `backend/tests/fixtures/expected_terminal_report.txt` and `expected_report.html` |
| Live verification | `scratchpad/phase-4/verify_live.py` — runs the real pipeline (not a re-implementation) against a live local Ollama server on all 3 mock runbooks |
| Dependencies added | `rich>=13.9`, `jinja2>=3.1` (`pyproject.toml`, `uv.lock`) |

## Design decisions
| # | Decision | Reason |
|---|---|---|
| P4-1 | The LLM sub-schema (`LlmAnalysis`) covers only `stepDependencies`, `singlePointsOfFailure`, `gapAnalysis` (restricted by prompt instruction to `MISSING_STEP`/`VAGUE_INSTRUCTION`), `suggestions`, `summary`, `riskScore` | Matches `llm-structured-output` skill and the Phase 0 finding that small models miss rule-checkable gaps; everything else is computed in `core/` |
| P4-2 | The final `riskScore` is the LLM's own value when available; the rule-based score (`core/risk_score.py`) is used only as the fallback when the LLM is unavailable, never blended with the LLM's score | The brief wants AI risk scoring; a blend would make both signals harder to reason about and to test deterministically. The rule-based score is a floor/fallback, not a second opinion averaged in |
| P4-3 | `MISSING_ROLLBACK` is checked against the whole `raw_markdown` document, not just parsed `Step.action` text | Phase 2's parser only turns a "Recovery Steps"/"Steps"/"Procedure" heading into `Step` objects; `estimate-service.md`'s rollback guidance lives under a separate "## Rollback" heading that is never parsed into steps. Checking only step text would wrongly flag the happy-path runbook as missing a rollback |
| P4-4 | Formatters live in a new top-level `formatters/` package, not `core/formatter.py` as the plan's prose literally suggests | `core/` and `health/` must not import `rich` (`.claude/rules/python-backend.md`, enforced by Phase 1's `test_package.py::test_framework_free_packages_import_cleanly`). Discovered this by running the full suite after first writing `core/formatter_terminal.py` — the pre-existing Phase 1 test failed immediately, which is exactly what it's there to catch |
| P4-5 | `OllamaProvider` requires an injected `random.Random` (no internal `random.Random()` default) | Matches `health/mock.py`'s existing convention and the DI rule ("RNG... passed in, never constructed inside core functions"); also avoids a real bandit `S311` finding instead of a false-positive one |
| P4-6 | `rto_analysis.py`'s `bottleneck_steps` is the minimal greedy set of longest steps whose removal would close the overage gap, not every step | A report listing "step 3 is a bottleneck" for a runbook with 20 min of slack is noise; the minimal set is what an SRE would actually cut first |
| P4-7 | `execution_plan.py` uses Kahn's-algorithm layering; if the merged dependency graph (parser + AI-inferred edges) has a cycle, every step still stuck after layering is flushed into one final phase instead of looping forever | AI-inferred `dependsOn` edges are not guaranteed acyclic the way the parser's are; a defensive fallback beats an infinite loop or a crash on live model output |
| P4-8 | LLM-inferred `stepDependencies` are merged into the parser's explicit `dependsOn`, filtered to known step numbers and non-self references, before being handed to `execution_plan.py` | The model can and does reference step numbers that don't exist (never observed live, but not excludable); `core/analyzer.py::_merged_depends_on` silently drops anything invalid rather than raising, since a malformed dependency hint is not a reason to fail the whole analysis |
| P4-9 | The Phase 4 orchestration function is named `run_analysis()`, not `analyze_runbook()` | `docs/IMPLEMENTATION_PLAN.md`'s own Phase 5 exit criterion says "both interfaces share one `analyze_runbook()` service function" — that name is reserved for the Phase 5 function that wraps parsing and health checks around this one. Caught and fixed mid-phase, after `analyze_runbook()` had already been written and tested once under that name |
| P4-10 | The analysis prompt's few-shot example uses angle-bracket placeholders (`"<what single person/system/step blocks recovery...>"`) for every value, not plausible concrete text | First live run against `qwen2.5:3b-instruct` copied the original example's concrete gap ("Step 4 says 'fix the database issue'" — lifted from the *payment-gateway* mock, not the runbook being analyzed) almost verbatim into the estimate-service report. Re-running after the fix produced grounded, runbook-specific findings instead (see live verification below) |
| P4-11 | `formatters/format_html.py` uses Jinja2 `select_autoescape`, not a raw string template | Runbook text is untrusted (`llm-and-security` rule) and several report fields (owner, gap descriptions, the LLM summary) can carry it through verbatim into HTML; escaping is mandatory, not a nice-to-have. Verified with `test_untrusted_text_is_html_escaped` |
| P4-12 | The golden end-to-end report and both formatter snapshots are generated with `FakeProvider` plus a fixed `clock`/`timer`, never a real LLM call | `testing.md`: "Never call a real LLM or real network in tests." The real-model run lives only in `scratchpad/phase-4/verify_live.py`, outside `pytest` |

## Exit criteria
| Criterion | Result | Evidence |
|---|---|---|
| Prompts as separate, versioned modules | Done | `llm/prompts/system.py`, `llm/prompts/analysis.py` |
| `LLMProvider` Protocol + Ollama implementation, JSON-schema constrained output | Done | `llm/base.py`, `llm/ollama.py` (uses Ollama's `format` parameter with `LlmAnalysis.model_json_schema()`) |
| One correction retry on Pydantic validation failure; 3 retries with exponential backoff on transport errors | Done | `llm/parse.py` (JSON-decode + validation retries), `llm/ollama.py` (transport retries); `test_llm_parse.py`, `test_ollama_provider.py` |
| Deterministic facts in code, LLM additive only | Done | `core/rto_analysis.py`, `core/execution_plan.py`, `core/gap_rules.py`, `core/risk_score.py`; `core/analyzer.py` filters rule-owned gap types out of LLM output |
| Rule-based fallback score | Done | `core/risk_score.py::compute_rule_based_score`, used in `run_analysis()` when `ai_analysis_available` is `False` |
| Graceful degradation with "AI analysis unavailable" note | Done | `core/analyzer.py`; `test_graceful_degradation_on_llm_failure`, `test_degraded_report_still_includes_rule_based_gaps` |
| Formatters: Rich terminal, JSON, HTML | Done | `formatters/format_terminal.py`, `formatters/format_json.py`, `formatters/format_html.py` |
| Tests: valid / malformed / schema-invalid-then-corrected / transport failure | Done | `test_llm_parse.py`, `test_ollama_provider.py`, `test_fake_provider.py`, `test_analyzer.py` |
| Snapshot tests for formatters | Done | `test_formatter_terminal.py`, `test_formatter_html.py` against `backend/tests/fixtures/expected_terminal_report.txt` / `expected_report.html` |
| Golden report in `expected-reports` | Done | `mock-data/expected-reports/estimate-service.json`; `test_golden_report.py` |
| Coverage above 80% | Done | 98.84% total (1125 statements, 258 branches), 241 tests |
| Lint clean | Done | `uv run poe lint`: ruff check, ruff format --check, mypy --strict all pass on 45 source files |
| Files under 200 lines | Done | Largest new file `core/analyzer.py` at 118 lines |
| `core/` and `health/` framework-free (no `rich`) | Done | `test_package.py` passes; formatters moved to their own package after this test caught the first attempt (P4-4) |
| No `Any`, no bare `except` | Done | mypy --strict clean; guard_files.py hook active throughout |
| End-to-end analyze works on all 3 runbooks with local model | Done | `scratchpad/phase-4/verify_live.py` against a live local Ollama server — see below |

## Live model verification
Ran the actual production pipeline (not a re-implementation) against a live
local Ollama server (`http://localhost:11434`, confirmed reachable and
serving `qwen2.5:3b-instruct` and `qwen2.5:7b-instruct` before starting).

**`qwen2.5:3b-instruct`** (fast dev model), all 3 mock runbooks, each with its
brief-matched inventory (estimate-service+healthy, payment-gateway+partial-outage,
auth-service+major-outage):

| Runbook | Wall time | RTO feasible | Rule gap types found | LLM SPOFs | Risk score |
|---|---|---|---|---|---|
| estimate-service.md | ~54s | true | (none — happy path) | 0 | 60 |
| payment-gateway.md | ~91s | **false** | MISSING_ROLLBACK, NO_VALIDATION, OWNER_AMBIGUITY, UNVERIFIED_DEPENDENCY | 1 | 75 |
| auth-service.md | ~38s | **false** | MISSING_ROLLBACK, NO_VALIDATION | 0 | 60 |

All three: valid JSON on the first try (no correction retries needed),
`aiAnalysisAvailable: true`, execution plan built successfully from the
merged `dependsOn` graph. The rule-based gaps landed exactly where the brief
predicted (payment-gateway: `team`-owned steps -> `OWNER_AMBIGUITY`, no
validation commands -> `NO_VALIDATION`, `card-network-gateway` not in any
inventory -> `UNVERIFIED_DEPENDENCY`; auth-service: 60 min of steps vs 15 min
RTO -> infeasible, single owner for everything -> flagged by the LLM as a
SPOF once the prompt fix landed).

**`qwen2.5:7b-instruct`** (the configured default), same 3 runbook/inventory pairs:

| Runbook | Wall time | RTO feasible | Rule gap types found | LLM SPOFs | Risk score |
|---|---|---|---|---|---|
| estimate-service.md | ~284s | true | (none — happy path) | 3 | 75 |
| payment-gateway.md | ~253s | **false** | MISSING_ROLLBACK, NO_VALIDATION, OWNER_AMBIGUITY, UNVERIFIED_DEPENDENCY | 2 | 75 |
| auth-service.md | ~199s | **false** | MISSING_ROLLBACK, NO_VALIDATION | 2 | **85 (CRITICAL)** |

All three valid on the first try, `aiAnalysisAvailable: true`. Per-call latency
(~200-285s) is higher than Phase 0's spike (~130-145s) because this prompt
embeds the full parsed runbook, dependency health and rule-gap JSON rather
than Phase 0's short inline text, and `max_tokens=2048` vs. Phase 0's 1800 --
consistent with a CPU-only 7B model at ~5 tokens/s, not a regression.
auth-service (the brief's "critical gaps" runbook: 60 min of steps against a
15-minute RTO, one owner for every step, no rollback, 4/7 inventory services
down) correctly comes out `CRITICAL`, distinctly above the other two, and the
gap summary for estimate-service (the happy-path runbook) is grounded and
specific to its actual steps -- no repeat of the P4-10 example-copying issue.

Full JSON reports for every run are in `scratchpad/phase-4/results/`.

## Caveats and follow-ups
- The first live run surfaced a real prompt-engineering bug (P4-10): a
  concrete-sounding few-shot example got copied almost verbatim into an
  unrelated report. Fixed by making every example value an angle-bracket
  placeholder plus an explicit "never copy this wording" instruction.
  Re-verified live after the fix.
- Small local models' `riskScore` judgement is still weak evidence on its
  own (Phase 0 already flagged this): scores clustered in the 60-75 range
  across runbooks of visibly different severity on the 3B model. This is why
  the deterministic rule-based score exists as the fallback, and why the
  report's other fields (RTO feasibility, rule-based gaps, dependency health)
  are the more trustworthy signal. Not a Phase 4 defect — the hybrid design
  exists specifically because of this limitation.
- `run_analysis()` takes an already-parsed `Runbook` and already-computed
  `DependencyHealth`, not file paths — wiring parsing, health checks and this
  function together behind one `analyze_runbook()` service function is
  Phase 5's job, alongside the CLI and API that will call it.
- `formatters/format_terminal.py`'s `render_terminal()` returns plain text by
  default (no ANSI) when not given a real `Console` — this is what keeps
  snapshot tests deterministic. The CLI (Phase 5) should pass a real stdout
  `Console` for actual color, and should avoid plain `print()` of a
  Rich-rendered string on a legacy Windows (cp1252) console, since Unicode
  box-drawing characters can raise `UnicodeEncodeError` there — `box.ASCII` is
  already used for exactly this reason, but the CLI should still write via a
  real `Console` (which handles Windows terminals correctly) rather than
  `print()`.
- `mock-data/expected-reports/` now has exactly one golden report
  (estimate-service). Phase 5/6 can add the other two if useful for a demo,
  but nothing currently requires them.

## Commands verified
```
uv add rich jinja2
uv run poe format
uv run poe lint     # ruff + format check + mypy --strict
uv run poe test     # pytest --cov, fail under 80% (actual: 98.84%)
uv run python scratchpad/phase-4/verify_live.py qwen2.5:3b-instruct
uv run python scratchpad/phase-4/verify_live.py qwen2.5:7b-instruct
```
