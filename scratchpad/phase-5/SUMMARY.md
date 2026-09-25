# Phase 5 Summary: CLI and REST API

Date: 2026-09-23. Status: **Done**.

## Phase 0/1/2/3/4 validation (done first)
Re-ran the full gate before starting: `uv run poe lint` (ruff check, ruff
format --check, mypy --strict on 45 files) and `uv run poe test` — both green,
241 tests, 98.84% coverage, matching `scratchpad/phase-4/SUMMARY.md` exactly.
Cross-checked `docs/IMPLEMENTATION_PLAN.md` and `README.md` against the repo:
every Phase 0-4 deliverable exists (3 runbooks, 3 inventories, golden report,
formatter snapshots, `llm/`, `health/`, `core/` modules, Phase 0 spike results,
Phase 4 live results). No discrepancies found. Ollama was reachable with
`qwen2.5:3b-instruct` and `qwen2.5:7b-instruct` pulled.

## What was built
| Area | Files |
|---|---|
| Shared service layer | `service.py`: `parse_markdown()` (timed, logs counts not content), `analyze_runbook(runbook, inventory, *, llm, checker, labels)` (dependency health check + `run_analysis()`, whole-pipeline `analysisTimeMs`, one `analysis_completed` log line with per-stage timings), `validate_inventory()`. Framework-free (guarded by `test_package.py`) |
| Boundary loaders | `loaders.py`: `read_text_file`, `decode_utf8`, `inventory_from_text/_data`, `load_inventory`, `error_summary` (Pydantic errors as `loc/msg/type` only) |
| Composition root | `wiring.py`: `build_llm(settings, client, rng)`, `build_checker(settings, client, rng, chaos=)` — the only place concrete providers are picked |
| New provider | `llm/disabled.py`: `DisabledProvider` for `LLM_PROVIDER=none` (fails fast with `AnalysisError` -> rule-based report) |
| CLI | `cli.py` (Typer app, `main(argv) -> int`, `run()` console script), `cli_output.py` (format enums, render/write helpers), `formatters/format_health.py` (`validate` output) |
| API | `api/app.py` (factory + lifespan), `api/routes.py`, `api/jobs.py` (in-memory `JobStore`), `api/body.py` (JSON/multipart reader with size caps), `api/paths.py` (allow-list), `api/errors.py` (status map + handlers), `api/middleware.py` (request/correlation ids, access log), `api/schemas.py`, `api/deps.py`, `api/openapi.py`, `api/__main__.py` (Uvicorn) |
| Errors | `utils/errors.py`: `BadRequestError`, `PathNotAllowedError`, `NotFoundError`, `PayloadTooLargeError`, `CapacityError` (all `AppError` subclasses with stable codes) |
| Config | `config.py`: `HEALTH_CHECKER`, `HEALTH_CHECK_CHAOS`, `LLM_PROVIDER=none`, `LLM_TIMEOUT_SECONDS`, `API_HOST`, `API_ALLOWED_DIR`, `API_MAX_UPLOAD_BYTES`, `API_WAIT_TIMEOUT_SECONDS`, `API_MAX_CONCURRENT_JOBS`, `API_MAX_STORED_JOBS`, `CORS_ORIGINS`; `.env.example` updated |
| Logging | `utils/logging.py`: `configure_logging(level, stream=)` so the CLI logs to stderr |
| Tooling | `pyproject.toml`: `[project.scripts] dr-agent`, `poe dev-api`; deps `fastapi`, `uvicorn`, `python-multipart`, `typer`; dev dep `httpx2` |
| Tests | 12 new test files (4 integration, 8 unit incl. extended `test_config.py`/`test_package.py`), 118 new tests (359 total), 98.75% coverage |

## Design decisions
| # | Decision | Reason |
|---|---|---|
| P5-1 | The shared service is two functions, `parse_markdown()` then `analyze_runbook(runbook: Runbook, ...)`, not one taking raw Markdown | The API must reject an unparseable runbook with 422 *before* queueing a minutes-long job, without parsing twice. Both CLI and API call exactly these two functions, which satisfies the "one shared `analyze_runbook()`" exit criterion |
| P5-2 | `service.py`, `loaders.py`, `wiring.py` live at the package top level, not in `core/` | `core/` is pure analysis logic; these orchestrate `health/` + `core/` + I/O. Still framework-free, now enforced by a new `test_package.py` case |
| P5-3 | `LLM_PROVIDER=none` added (`DisabledProvider`) | Gives an honest, instant, model-free mode (CI gates, offline demos) and lets the subprocess CLI test run with no network and no monkeypatching. It reuses the existing graceful-degradation path instead of a new code path |
| P5-4 | Usage errors exit 1, not Click's default 2 | The brief reserves 2 for "critical risk". `main()` runs Typer with `standalone_mode=False` and maps `TyperException`/`Abort` to 1. Found live: Typer 0.27 vendors its own Click (`typer._click`), so catching `click.ClickException` silently missed usage errors — switched to the public `typer.TyperException`, and removed the unused `click` import |
| P5-5 | CLI: report to stdout; spinner, logs and errors to stderr; logs default to `warning` unless `--verbose` | `dr-agent analyze -f json > report.json` must produce valid JSON (asserted in tests), and structlog's JSON lines would otherwise interleave with the Rich report |
| P5-6 | `--output` writes plain text for the terminal format; stdout uses a real Rich `Console` | Follows the Phase 4 caveat: color only on a real console, never ANSI codes in files, and no `print()` of Rich text on legacy Windows consoles |
| P5-7 | `analyze --inventory` is optional; without it every dependency is `NOT_IN_INVENTORY` and `meta.inventoryFile` is `(none)` | The brief marks it optional. Reporting "unverified" is honest; pretending dependencies are UP would hide risk |
| P5-8 | API is job-based: 202 + `Location`, `GET /jobs/{id}`, `?wait=true` bounded by `API_WAIT_TIMEOUT_SECONDS` returning the bare report with 200 | Plan decision D3 (7B on CPU takes 3-5 min, beyond sensible HTTP timeouts) while still offering the brief's "response: DRReadinessReport" shape for short runs. `?wait=true` on the job endpoint gives long-polling, which also makes tests deterministic without sleep loops |
| P5-9 | `JobStore`: semaphore (default 1 concurrent), bounded store (default 100) evicting oldest finished jobs, `429 CAPACITY_EXCEEDED` when full of unfinished jobs; shutdown cancels running jobs (`CANCELLED`) | Ollama serves one CPU generation at a time anyway; bounded memory and explicit backpressure instead of an unbounded queue. In-memory only (no persistence in the PoC, plan question 3) |
| P5-10 | One path, two content types: the route reads the body itself (`api/body.py`) and `api/openapi.py` documents both in OpenAPI, registering `AnalyzeJsonRequest` + `$defs` under `components.schemas` | FastAPI cannot declare JSON-or-multipart for one operation. Phase 6 generates its typed client from `/openapi.json`, so the schema must be complete (asserted in tests) |
| P5-11 | Size caps: JSON body streamed and cut at `API_MAX_UPLOAD_BYTES`; multipart checked against the declared Content-Length (2x cap + 64 KiB) and then per file | A cap per uploaded file matches the setting's meaning; streaming the JSON body avoids reading an oversized body into memory |
| P5-12 | Path allow-list: `(base / requested).resolve()` must stay inside the resolved `API_ALLOWED_DIR` and end in `.md/.markdown` (runbook) or `.json` (inventory); paths are relative to the allowed dir; errors echo only the client's string | Tested for `..`, absolute paths and null bytes; symlinks and drive letters are handled by the same resolve-then-contain check but not separately tested. The extension allow-list stops the endpoint being used to read arbitrary files that happen to live inside the directory |
| P5-13 | Errors never leak internals: Pydantic details trimmed to `loc/msg/type` (no `input`), no absolute paths in `NotFoundError`, unhandled exceptions become a generic `500 INTERNAL_ERROR` (logged server-side), all details JSON-safe (`json_safe`) | `input` can be large untrusted runbook text; `ParseError` details can carry exception objects from validators, which would otherwise crash the JSON response |
| P5-14 | Request/correlation ids from clients are accepted only if they match `^[A-Za-z0-9._-]{1,64}$`, otherwise regenerated; bound via structlog contextvars, which background jobs inherit | Prevents log/header injection; verified live that the job's `analysis_completed` line carries the originating `request_id` |

## Exit criteria
| Criterion | Result | Evidence |
|---|---|---|
| CLI `analyze`, `validate`, `parse`, `version` | Done | `cli.py`; `test_cli.py` (19 tests) |
| `--format json\|terminal\|html`, spinner | Done | `cli_output.py`; `test_analyze_writes_output_file`, JSON-on-stdout test |
| Exit codes 0 / 1 / 2 (>80) | Done | `test_analyze_json_is_clean_stdout_and_critical_exits_2`, `test_score_of_exactly_80_is_not_critical`, `test_errors_exit_1_with_shared_shape_on_stderr`, `test_main_maps_usage_errors_to_1`, subprocess `test_exit_codes` |
| `POST /api/v1/dr/analyze` multipart + JSON, job id, `GET /jobs/{id}`, `?wait=true` | Done | `test_api_analyze.py` (23 tests) |
| `GET /api/v1/dr/analyze` allow-listed paths | Done | `test_get_analyze_reads_allow_listed_files`, `test_get_analyze_rejects_bad_paths`, `test_api_paths_errors.py` |
| `GET /api/v1/health` | Done | `test_health_endpoint` |
| CORS, request-ID middleware, `{error, code, details?}`, graceful shutdown, upload limits, OpenAPI | Done | `test_api_platform.py` (13 tests) |
| Integration tests: CLI via subprocess, API via TestClient | Done | `test_cli_subprocess.py`, `test_api_*.py` |
| Plan verification: auth-service + major-outage exits 2 on a live model | **Not met** | Exit-code logic correct and tested, but live scores were 75 (7B) / 50 (3B) / 80 (rules). See live verification |
| Both interfaces share one `analyze_runbook()` | Done | `cli.py::_analyze` and `api/routes.py::_submit` both call `service.analyze_runbook()`; `test_shared_service_modules_are_framework_free` |
| Coverage > 80% | Done | 98.75% (1822 statements, 336 branches), 359 tests |
| Lint clean | Done | ruff check, ruff format --check, mypy --strict on 63 source files |
| Files under 200 lines | Done | Largest source file `cli.py` at 172 lines (split `cli_output.py` out after the formatter pushed it to 207); largest test file 183 |
| No `Any`, no bare `except` | Done | mypy --strict; `guard_files.py` hook; the one broad `except Exception` is the job task boundary (`api/jobs.py`), which records and logs the error |

## Live verification
All runs go through the real `dr-agent` console script (or the real Uvicorn
server) against the local Ollama server, using the same runbook/inventory pairs
as Phase 4. Full JSON reports are in `scratchpad/phase-5/results/`.

**CLI, `qwen2.5:7b-instruct` (default model)**

| Runbook + inventory | Wall time | Exit | Risk score | RTO feasible | Gap types | SPOFs |
|---|---|---|---|---|---|---|
| auth-service + major-outage | 160 s | 0 | 75 (HIGH) | false | MISSING_ROLLBACK, NO_VALIDATION, VAGUE_INSTRUCTION | 2 |
| estimate-service + healthy | 143 s | 0 | 75 (HIGH) | true | VAGUE_INSTRUCTION | 1 |
| payment-gateway + partial-outage | 189 s | 0 | 75 (HIGH) | false | MISSING_ROLLBACK, MISSING_STEP, NO_VALIDATION, OWNER_AMBIGUITY, UNVERIFIED_DEPENDENCY, VAGUE_INSTRUCTION | 2 |

**CLI, `qwen2.5:3b-instruct`**

| Runbook + inventory | Wall time | Exit | Risk score | RTO feasible | Gap types | SPOFs |
|---|---|---|---|---|---|---|
| auth-service + major-outage | 80 s | 0 | 50 (MEDIUM) | false | MISSING_ROLLBACK, NO_VALIDATION, VAGUE_INSTRUCTION | 1 |
| estimate-service + healthy | 66 s | 0 | 60 (HIGH) | true | MISSING_STEP | 0 |
| payment-gateway + partial-outage | 52 s | 0 | 75 (HIGH) | false | MISSING_ROLLBACK, NO_VALIDATION, OWNER_AMBIGUITY, UNVERIFIED_DEPENDENCY | 0 |

Every run: valid model output on the first try, `aiAnalysisAvailable: true`,
report JSON written via `--output`, deterministic parts identical to Phase 4
(RTO feasibility, rule-owned gaps, dependency health).

**API, `qwen2.5:3b-instruct`**: `POST /api/v1/dr/analyze` (multipart,
payment-gateway + partial-outage) -> `202 pending`; immediate `GET /jobs/{id}`
-> `running`; `GET /jobs/{id}?wait=true` -> `succeeded` with the embedded
report (risk 75, `aiAnalysisAvailable: true`, `analysisTimeMs` about 55 s).
Saved as `results/api_qwen2.5_3b-instruct_payment-gateway_job.json`.

**Graceful degradation, live**: `LLM_BASE_URL=http://127.0.0.1:9` (nothing
listening) -> after the provider's 3 transport retries with backoff, a
rule-based report with `AI analysis unavailable: Ollama request failed after
retries`, exit 0, 13 s total.

**Rule-based mode** (`LLM_PROVIDER=none`): instant; auth-service +
major-outage = 80 (HIGH), exit 0.

### Plan verification check that did NOT pass: "auth-service + major-outage exits 2"
`docs/IMPLEMENTATION_PLAN.md`'s Verification section expects exit code 2
(critical risk) for auth-service + major-outage. The exit-code logic is correct
and tested (`> 80` -> 2, `== 80` -> 0), but no live configuration produced a
score above 80:

- 7B scored it **75** this run, **85** in Phase 4, on an identical prompt
  (Phase 5 only wraps `run_analysis()`; file labels are not in the prompt).
  So the model's own score varies by about 10 points between runs even at
  `temperature=0` (no `seed` is passed to Ollama; CPU inference is not
  bit-for-bit reproducible).
- 3B scored it **50 (MEDIUM)**, *below* the happy-path estimate-service (60).
- The rule-based fallback gives exactly **80**, one point short.

This is the weakness Phases 0 and 4 already recorded (small local models'
`riskScore` does not track severity), now visible at the exit-code boundary.
P4-2 made the LLM's score final whenever it is available. Also,
`core/risk_score.py`'s docstring calls the rule score a "fallback and floor",
but `core/analyzer.py` never applies it as a floor. That was not changed
here, since it is a Phase 4 scoring decision, not an interface one.
Options for the user are listed in the caveats.

## Caveats and follow-ups
- **Open decision (risk-score reliability):** see the "did NOT pass" note
  above. Options: (a) use `max(llm_score, rule_score)`, which makes the rule
  score a real floor as its docstring already claims (auth-service would then be 80,
  still not > 80); (b) additionally tune the rule weights so an infeasible RTO
  plus two HIGH gaps and 5 unhealthy inventory services lands above 80; (c) pass
  a fixed `seed` in Ollama `options` for reproducible runs; (d) accept it and
  change the plan's verification line. Not changed without the user's decision.
- Jobs live in memory: a restart loses them, and running more than one API
  process would need a shared store. Fine for the PoC (plan question 3).
- Multipart bodies without a Content-Length (chunked) are still parsed by
  Starlette (spooled to disk) before the per-file cap applies. Uvicorn behind a
  reverse proxy with a body limit is the Phase 7 answer.
- `API_ALLOWED_DIR` and `.env` are resolved relative to the working directory,
  so `dev-api` should be started from the repo root (the Docker image in Phase 7
  will set an absolute path).
- Starlette 1.6's TestClient prefers `httpx2` (added as a dev dependency, BSD-3,
  pydantic org). One remaining third-party `DeprecationWarning` (anyio
  `BlockingPortal` alias inside Starlette) is not ours to fix.
- Phase 6 needs: an HTML export endpoint or client-side rendering (the Jinja2
  HTML formatter is only reachable from the CLI today), and CORS already allows
  the Vite dev origin `http://localhost:5173`.

## Commands verified
```
uv add fastapi uvicorn python-multipart typer
uv add --dev httpx2
uv run poe format
uv run poe lint     # ruff + format check + mypy --strict
uv run poe test     # pytest --cov, fail under 80% (actual: 98.75%)
LLM_PROVIDER=none uv run dr-agent analyze -r mock-data/runbooks/auth-service.md -i mock-data/inventories/major-outage.json
LLM_PROVIDER=none PORT=8765 uv run poe dev-api   # + curl smoke tests (multipart, JSON, GET paths, traversal, 404s, OpenAPI)
LLM_MODEL=<model> uv run dr-agent analyze -r ... -i ... -f json -o scratchpad/phase-5/results/<model>_<runbook>.json
LLM_MODEL=qwen2.5:3b-instruct PORT=8766 uv run poe dev-api   # + live POST/poll job
LLM_BASE_URL=http://127.0.0.1:9 uv run dr-agent analyze -r mock-data/runbooks/auth-service.md -i mock-data/inventories/major-outage.json
```
