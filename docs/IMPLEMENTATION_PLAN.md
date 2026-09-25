# AI-Powered DR Readiness Agent: Phased Plan (Python + React, fully open source)

## Context
The brief (`AI-Powered Disaster.md`) asks for a tool that parses Markdown DR runbooks, checks their dependencies against a health inventory, and produces an AI-generated readiness report (risk score, RTO feasibility, SPOFs, gaps, execution plan). The brief specifies Node/TypeScript and the Claude API. You asked for Python + React and open source only, so the stack is translated and the LLM becomes a local open-source model. All functional requirements, report schema, mock data and quality bars from the brief are kept.

## Stack mapping (brief -> open-source equivalent)
| Brief | This plan |
|---|---|
| Node 20 + TypeScript strict | Python 3.12, `mypy --strict`, no `Any` |
| commander CLI | Typer (+ Rich for colored terminal output and spinner) |
| fastify + multipart + cors | FastAPI + python-multipart + CORSMiddleware, Uvicorn |
| zod | Pydantic v2 |
| unified/remark | `markdown-it-py` (token AST) plus regex fallbacks |
| @anthropic-ai/sdk tool_use | `LLMProvider` interface; default Ollama (Qwen2.5 14B or Llama 3.1 8B) using JSON-schema constrained output via `ollama` / OpenAI-compatible client |
| fetch + AbortController | `httpx` async + `asyncio.wait_for` |
| pino | `structlog` (JSON logs, request/correlation IDs) |
| vitest | pytest + pytest-asyncio + pytest-cov (>80%); vitest + React Testing Library for UI |
| tsup / eslint / prettier | `uv` or Poetry, ruff (lint+format), mypy; UI: Vite, eslint, prettier |
| (new) | React 18 + TypeScript + Vite + Tailwind + Recharts dashboard |
| (new) | Docker Compose (api, ui, ollama), GitHub Actions CI |

## Proposed layout
```
dr-readiness-agent/
  README.md, pyproject.toml, docker-compose.yml, .env.example, Makefile
  backend/src/dr_agent/
    config.py            # pydantic-settings, fail fast
    models/              # runbook.py, inventory.py, report.py
    core/                # parser.py, validator.py, analyzer.py, formatter.py (no web imports)
    health/              # base.py (Protocol), mock.py, live.py
    llm/                 # base.py (Protocol), ollama.py, prompts/{system,analysis}.py
    api/                 # app.py, routes.py, deps.py, errors.py
    cli.py
    utils/               # logging.py, errors.py, timing.py
  backend/tests/{unit,integration,fixtures}
  mock-data/{runbooks,inventories,expected-reports}
  frontend/ (Vite React app)
```
Rule kept from brief: files under 200 lines, core has no framework imports, providers injected via dependency injection.

## Phases

### Phase 0: Decisions and spikes (0.5 day) — DONE 2026-09-21
- [x] Confirm open questions below (plan defaults kept, see decisions in the summary).
- [x] Spike: Ollama installed; qwen2.5 7B and 3B tested with JSON-schema constrained output on a trimmed report schema; latency measured on target hardware (CPU only, 16 GB RAM).
- [x] Exit: model + hardware decision recorded in `scratchpad/phase-0/SUMMARY.md`.
- Result: 4 of 4 runs schema-valid; 7B about 5 tokens/s and 130-145 s per call; both models missed rule-checkable gaps (ambiguous owners, no validation). Decisions D1-D9 in the summary:
  - default model `qwen2.5:7b-instruct`, 3B as a fast dev option
  - rule-based gap detection in code, LLM additive
  - job-based async analyze API (POST returns job id, poll for result)
  - Python 3.12 pinned; `poethepoet` tasks instead of Makefile (no `make` on this machine)
  - Docker not installed here, so Compose is authored but unverified locally

### Phase 1: Foundation — DONE 2026-09-21
- [x] Repo scaffolding, uv (Python 3.12 pinned), ruff, mypy strict, pytest config, pre-commit, `poethepoet` tasks (`uv run poe test|lint|format`) instead of a Makefile. `dev-api` lands in Phase 5 (no FastAPI yet), vitest in `poe test` in Phase 6.
- [x] `config.py` (pydantic-settings; fail fast on invalid values; defaults PORT=8000, LOG_LEVEL, HEALTH_CHECK_TIMEOUT_MS=3000, LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL, LLM_MAX_TOKENS).
- [x] structlog setup, typed error hierarchy (`AppError` -> `ParseError`, `ValidationError`, `AnalysisError`, `ConfigError`), timing utility.
- [x] Pydantic models exactly per brief: Runbook/Step/Dependency, SystemInventory/Service, DRReadinessReport (riskLevel derived from score), plus `ServiceStatus` and `parserWarnings`.
- [x] Exit: models unit-tested (91 tests, 100% coverage); lint and mypy strict clean. CI workflow authored but not yet run remotely (directory is not a git repo).
- Result and decisions P1-1 to P1-11 in `scratchpad/phase-1/SUMMARY.md`.

### Phase 2: Markdown parser + mock runbooks — DONE 2026-09-22
- [x] Parse with markdown-it-py (`SyntaxTreeNode` tree, table rule enabled): H1 -> service; bold/inline-code/table/`Key: value` patterns -> Owner/RTO/RPO (units: min/hours/`1h 30m`/ranges normalized to minutes); "Dependencies" section (list or table); "Recovery Steps" ordered/bullet lists or a table; step owner/time/target/validation-command extraction.
- [x] Regex fallbacks over plain-text lines, sensible defaults, `parserWarnings`, Pydantic validation -> `ParseError`.
- [x] Created the 3 mock runbooks (estimate-service happy path, payment-gateway 2 "team"-owned steps + 45 min work vs 30 min RTO, auth-service single-owner bus factor + no Dependencies section + 60 min work vs 15 min RTO) plus 6 fixtures for malformed, empty, headerless, mixed-time-unit, table-based and bullet-based input.
- [x] Note: step `dependsOn` is inferred by the LLM per brief; the parser only fills it from explicit "after step N[, and step M]" phrases.
- Exit: parser tests cover every documented variant and edge case (151 tests total, 99% coverage). Decisions P2-1 to P2-10 in `scratchpad/phase-2/SUMMARY.md`.

### Phase 3: Health validator — DONE 2026-09-22
- [x] `HealthChecker` Protocol; `MockHealthChecker` (reads mock status from inventory, 50-200 ms random latency or an explicit `mockLatencyMs` override, `chaos` flag with a configurable failure rate, default 20%, overriding to `UNREACHABLE`); `LiveHealthChecker` (injected `httpx.AsyncClient`, per-request timeout, `asyncio.gather(return_exceptions=True)`).
- [x] Inventory's `mockStatus` field (added in Phase 1) drives `MockHealthChecker`; optional `mockLatencyMs` also from Phase 1.
- [x] 3 mock inventories (healthy = all UP, partial-outage = 2/7 down, major-outage = 4/7 down + 1 unreachable, same 7 service names across all 3); `health/dependency_check.py` cross-matches `Runbook.dependencies` to the inventory case-insensitively, emitting `NOT_IN_INVENTORY` for unmatched names (e.g. payment-gateway's `card-network-gateway`, deliberately absent from all 3 inventories).
- Exit: tests for UP/DOWN/UNREACHABLE/timeout, parallelism, chaos determinism (seeded RNG) — 185 tests total, 99.09% coverage. Decisions P3-1 to P3-10 in `scratchpad/phase-3/SUMMARY.md`.

### Phase 4: LLM analysis + report formatting — DONE 2026-09-22
- [x] Prompts as separate modules (`llm/prompts/system.py`, `llm/prompts/analysis.py`); system prompt per brief (senior SRE, always find at least one improvement, untrusted-data stance for `<runbook>`/`<validation>`).
- [x] `LLMProvider` Protocol (`llm/base.py`) + `OllamaProvider` (`llm/ollama.py`, JSON-schema constrained via Ollama's `format`, 3 retries with exponential backoff + jitter on transport errors) + `FakeProvider` (`llm/fake.py`) for tests. `llm/parse.py` does the JSON-decode retry and the schema-validation retry (one each) on top of the provider.
- [x] Reliability strategy for smaller open models: deterministic facts computed in `core/` (`rto_analysis.py`, `execution_plan.py`, `gap_rules.py`, `risk_score.py`); the LLM (`llm/schemas.py: LlmAnalysis`) is asked only for `stepDependencies`, `singlePointsOfFailure`, `gapAnalysis` (MISSING_STEP/VAGUE_INSTRUCTION only), `suggestions`, `summary`, `riskScore`. `core/analyzer.py` merges and validates; the rule-based score is the fallback used only when the LLM is unavailable, not a blend.
- [x] Phase 0 finding confirmed live: `OWNER_AMBIGUITY`, `NO_VALIDATION`, `MISSING_ROLLBACK`, `UNVERIFIED_DEPENDENCY` are detected by `core/gap_rules.py`; the LLM is instructed never to emit these types, and `core/analyzer.py` drops them from the LLM output defensively even if it does.
- [x] Graceful degradation: on `AnalysisError` (transport failure surviving the provider's retries, or malformed/invalid output surviving `llm/parse.py`'s retries), `core/analyzer.py: run_analysis()` returns rule-based-only results with `aiAnalysisAvailable: false` and an `aiNote`. (Named `run_analysis`, not `analyze_runbook`, to leave that name free for Phase 5's shared parse+health-check+analyze+format service function.)
- [x] Formatters (`formatters/`, outside `core/` -- `rich` is a forbidden import in `core/`/`health/` per `test_package.py` and `.claude/rules/python-backend.md`): `format_terminal.py` (Rich, ASCII table borders, color-coded risk score), `format_json.py`, `format_html.py` (Jinja2, autoescaped -- runbook text is untrusted).
- [x] Tests with `FakeProvider`: valid, malformed-JSON-then-corrected, schema-invalid-then-corrected, transport failure, graceful degradation; `httpx.MockTransport` tests for `OllamaProvider`'s retry/backoff; snapshot tests for both formatters (`backend/tests/fixtures/expected_terminal_report.txt`, `expected_report.html`); golden end-to-end report in `mock-data/expected-reports/estimate-service.json`.
- Exit: end-to-end analyze verified on all 3 runbooks against a live local model (both `qwen2.5:3b-instruct` and the default `qwen2.5:7b-instruct`) -- see `scratchpad/phase-4/SUMMARY.md`.

### Phase 5: Interfaces — DONE 2026-09-23
- [x] Shared service layer (`service.py`, framework-free): `parse_markdown()` + `analyze_runbook()` (dependency health check + `run_analysis()`, whole-pipeline timing) + `validate_inventory()`; `loaders.py` (files/uploads/JSON -> validated models or typed errors); `wiring.py` (the one composition root that builds `LLMProvider`/`HealthChecker` from settings).
- [x] CLI (Typer, `dr-agent` console script): `analyze`, `validate`, `parse`, `version`; `--format json|terminal|html`, `--output`, `--chaos`, `--verbose`; Rich spinner on stderr; logs on stderr so stdout pipes cleanly; exit codes 0 ok, 1 error (usage errors too, remapped from Click's 2), 2 risk score >80.
- [x] FastAPI: `POST /api/v1/dr/analyze` (multipart `runbook` + optional `inventory` files, or JSON `{runbookMarkdown, inventory?, runbookName?}`) returns 202 + job id + `Location`; `GET /api/v1/dr/jobs/{id}` to poll; `?wait=true` (bounded by `API_WAIT_TIMEOUT_SECONDS`) returns the report itself with 200 if done in time; `GET /api/v1/dr/analyze?runbook=&inventory=` restricted to `API_ALLOWED_DIR` (resolved-path containment check, extension allow-list); `GET /api/v1/health` `{status, version, uptime}`.
- [x] Request-ID/correlation-ID middleware (sanitised client ids, bound into structlog context incl. background jobs), CORS (`CORS_ORIGINS`), global error shape `{error, code, details?}` for app, validation, HTTP and unhandled errors, graceful shutdown (lifespan cancels unfinished jobs, closes the shared httpx client), upload/body size cap (`API_MAX_UPLOAD_BYTES`), job concurrency cap and backpressure (429), OpenAPI documents both request body types.
- [x] New settings: `HEALTH_CHECKER` (mock|live), `HEALTH_CHECK_CHAOS`, `LLM_PROVIDER=none` (rule-based only), `LLM_TIMEOUT_SECONDS`, `API_*`, `CORS_ORIGINS`. `uv run poe dev-api` serves the API.
- [x] Integration tests: API via `TestClient` (lifespan running), CLI via `CliRunner` plus a subprocess exit-code test.
- Exit: CLI and API share `service.analyze_runbook()` — 359 tests (118 new), 98.75% coverage, lint clean; live-model verification in `scratchpad/phase-5/SUMMARY.md`. Decisions P5-1 to P5-14 there.

### Phase 6: React dashboard — DONE 2026-09-23
- [x] Vite + React 18 + TS (strict) + Tailwind 4 + Recharts; typed client generated from OpenAPI (`openapi-typescript` + `openapi-fetch`, `uv run poe gen-api`; the committed `frontend/openapi.json` is checked for drift by a backend test).
- [x] Screens: upload/paste runbook and inventory with a sample picker (new allow-listed `GET /api/v1/dr/samples[/file]`), risk gauge, RTO waterfall (phases + sequential total + RTO line, buffer/bottlenecks as text), dependency health table, SPOF list, gap list with severity filter, execution-plan phases, suggestions, executive summary, export JSON (client-side) and HTML (new `GET /api/v1/dr/jobs/{id}/report.html`, 409 while unfinished), loading (elapsed time, job id), error and AI-unavailable states.
- [x] Tests: vitest + RTL, 42 tests, 99.5% lines (80% thresholds enforced); backend 374 tests, 98.79%. `poe test`/`poe lint` now include vitest and eslint/tsc/prettier; CI installs Node and builds the UI. Playwright smoke test (optional) skipped; the demo was verified in Chromium through the Playwright MCP instead.
- Exit: full demo path works in the browser against mock data, both rule-only (`LLM_PROVIDER=none`) and with `qwen2.5:3b-instruct` (127 s, all sections populated). Decisions P6-1 to P6-11 and screenshots in `scratchpad/phase-6/`.

### Phase 7: Hardening and delivery -- DONE 2026-09-23 (Docker run pending, see exit)
- [x] Re-verified Phases 0-6 first: `poe lint` clean, `poe test` 377 backend tests (98.79%) + 42 UI tests, all files under 200 lines, CLI smoke on the 3 mock pairs.
- [x] Dockerfiles, multi-stage: `docker/api.Dockerfile` (uv `sync --frozen --no-dev --no-editable` into a venv, then a slim runtime, non-root, mock-data baked in, `HEALTHCHECK` on `/api/v1/health`) and `docker/ui.Dockerfile` (node build, then unprivileged nginx with `docker/nginx.conf`: SPA fallback, `/api/` proxied to the API, CSP and hardening headers, `/healthz`). The UI is built with an empty `VITE_API_BASE_URL`, so it runs same-origin with no CORS.
- [x] `docker-compose.yml`: `ollama` (volume, healthcheck), `ollama-pull` (one-shot `ollama pull $LLM_MODEL`), `api` and `ui`, ordered by health checks. Containers are read-only with `/tmp` tmpfs, `cap_drop: ALL` and `no-new-privileges`, ports bound to 127.0.0.1, and Ollama unpublished. `.dockerignore` added. Base image tags were checked against the registries (nginx moved from the stale 1.27 to 1.30).
- [x] GitHub Actions: the existing `quality` job (ruff, mypy, pytest `--cov-fail-under=80`, UI lint/test/build) plus `audit` (`poe audit`) and `docker` (compose config and build, then a rule-based smoke test through the UI proxy: health, GET analyze, CSP header). `permissions: contents: read`.
- [x] Security pass. Fixed: runbook text could forge the `</runbook>` prompt delimiter (now JSON with `<>&` unicode-escaped); URL credentials could appear in the Ollama error reason and in logs (now scrubbed, tracebacks included); no hardening headers (now on every API response, plus a strict CSP on the HTML report export). Reviewed and unchanged: input validation, size caps, path allow-list, error shape, request-id sanitising, autoescaping, no raw HTML in the UI. Documented: `HEALTH_CHECKER=live` is an SSRF surface; there is no auth or rate limiting. Audits: `pip-audit` (new dev dependency) and `npm audit` both report 0 vulnerabilities (`uv run poe audit`).
- [x] README: Docker run, deployment diagram, demo walkthrough (checked against actual rule-based output), guide to swapping in real integrations, expanded security notes, roadmap.
- Exit: **partial.** Docker is not installed on this machine, so `docker compose up` could not be run here. Evidence gathered instead: the wheel ships the Jinja template; the API ran with the container's settings from a directory holding only `mock-data`; the same-origin UI build was tested in Chromium behind a stand-in that sends the real `nginx.conf` headers and proxies `/api/` (no CSP violations, and analyze, poll and HTML export all work); the compose file was parsed and its references checked. The CI `docker` job is the remaining proof, on first push. Gate: 389 backend tests (98.80%), 43 UI tests, lint clean. Details and decisions P7-1 to P7-9 are in `scratchpad/phase-7/SUMMARY.md`.

### Post-PoC change: configurable hosted LLM -- 2026-09-23
- [x] `OpenAICompatibleProvider` (`llm/openai_compatible.py`): posts to `{LLM_BASE_URL}/chat/completions` with a bearer `LLM_API_KEY`, `response_format` `json_schema` (or `json_object` with the schema in the system prompt, via `LLM_RESPONSE_FORMAT`). Retries connection errors, timeouts, 408, 429 and 5xx with backoff (shared with Ollama in `llm/retry.py`); other 4xx fail fast. The key is scrubbed from error details. Plain httpx, no vendor SDK.
- [x] Config: `LLM_PROVIDER=ollama|openai_compatible|none`, `LLM_API_KEY` (`SecretStr`, required for `openai_compatible`, fail fast), `LLM_RESPONSE_FORMAT`. Switching provider needs no code change.
- [x] Docker Compose runs no local model: `ollama` and `ollama-pull` services and the model volume removed. The API defaults to `openai_compatible` against Mistral (`https://api.mistral.ai/v1`, `mistral-small-latest`) and exits with `CONFIG_ERROR` without `LLM_API_KEY`; `LLM_PROVIDER=none` still works for the CI smoke test.
- [x] Tests: `test_openai_compatible_provider.py` (payload, auth header, both response formats, retry/fail-fast matrix, key and URL-credential scrubbing, malformed responses), config and wiring tests.
- Not yet verified against the real OpenAI or Mistral API (no key on this machine).

## Execution phases (human-authorized runbook execution via MCP)
Design: [`docs/design/runbook-execution.md`](design/runbook-execution.md). Decisions: [`docs/adr/`](adr/README.md) (ADRs 0001-0006).
Decision log (2026-09-23, confirmed with the project owner): execution targets a bundled mock MCP server only; steps map to tool calls in a hybrid way (runbook `Tool:` annotations first, AI proposals that must be reviewed, otherwise manual); approvers are named without authentication, with two distinct approvers for destructive calls; documents are a design doc plus ADRs. New dependencies, both MIT: `mcp`, `jsonschema`.

### Phase 8: Execution design (documents only) -- DONE 2026-09-24 (approved)
- [x] Design doc: goals and non-goals, architecture and modules, annotation syntax, step and execution state machines, approval model, data model and restart recovery, API, CLI, UI, configuration and policy file, security notes, testing strategy, dependencies, rollout.
- [x] ADR index and template; ADRs 0001 (MCP SDK behind `ToolExecutor`), 0002 (hybrid step-to-tool mapping), 0003 (named approvers, two-person rule), 0004 (SQLite execution store), 0005 (bundled mock MCP server), 0006 (safety controls).
- [x] README roadmap updated; summary in `scratchpad/phase-8/SUMMARY.md`.
- [x] Exit: the project owner reviewed and approved the design and ADRs on 2026-09-24; the design and ADRs 0001-0006 are now Accepted.

### Phase 9: Execution core -- DONE 2026-09-24
- [x] `Step` gains optional `tool_call`, `verify_call`, `rollback_call` (`PlannedToolCall`); `core/annotations.py` reads `Tool:`, `Verify-Tool:`, `Rollback-Tool:` from nested list items and from `Tool` / `Verify Tool` / `Rollback Tool` table columns, warns on bad or duplicate annotations, and keeps annotation code spans out of `validation_command`.
- [x] `mock-data/runbooks/estimate-service-executable.md` (every step annotated for the `drsim` server; 2 rollback calls).
- [x] `execution/`: models, transition tables (`transitions.py`), planner (reuses `compute_execution_plan`; the dependency merge moved from `core/analyzer.py` to `core/dependency_graph.py`), policy file + checks (allow-list, `jsonschema` against `inputSchema`, constraints, risk raised by server hints, shell-like tool names refused), approvals (call hash, two-person rule), hash-chained audit, `ExecutionStore` + SQLite store, restart recovery.
- [x] `tools/base.py` (`ToolExecutor`, `ToolSpec`, `ToolResult` truncated to 16 KB), `tools/dry_run.py`, `tools/fake.py`.
- [x] Engine (`engine.py`, `runner.py`, `rollback.py`, `decisions.py`, `step_actions.py`) running the plan one call at a time against the dry-run and fake executors: approvals, verification, failure, retry, rollback, skip, manual, pause/resume, abort, approval timeout, max tool calls, capacity, re-check of policy and hashes right before each call.
- [x] New `AppError` subclasses (`EXECUTION_DISABLED`, `INVALID_TRANSITION`, `STALE_CALL`, `POLICY_VIOLATION`, `TOOL_ERROR`, mapped to 403/409/409/422/502) and settings (`EXECUTION_*`, `MCP_SERVERS_FILE`), disabled by default.
- Exit: met. Ruff and mypy --strict clean, 830 backend tests at 99.09% coverage, 43 UI tests, every file under 200 lines, golden report unchanged, both transition tables tested exhaustively (every state and event pair), `pip-audit` and `npm audit` clean. Decisions and deviations P9-1 to P9-10 in `scratchpad/phase-9/SUMMARY.md`.

### Phase 10: MCP integration -- DONE 2026-09-24
- [x] Re-verified Phases 0-9 first: lint clean, 830 backend tests (99.09%), 43 UI tests, no file over 200 lines.
- [x] `tools/mcp_executor.py` (+ `tools/mcp_convert.py`) with the MCP SDK (`mcp` 2.2.0, MIT): stdio, streamable HTTP and in-process servers through the SDK's `Client`; one owner task holds all connections (anyio requires closing them in the task that opened them); connect and list retried with backoff, `call_tool` never; results validated into `ToolResult` (16 KB) and tool listings into `ToolSpec`. `tools/servers_config.py` loads `MCP_SERVERS_FILE` (stdio/http, `${VAR}` resolution, secrets as `SecretStr`).
- [x] `mock_mcp/`: `drsim` server (`MCPServer`) with the nine tools from ADR 0005 and their MCP annotations, in-memory `DrEnvironment` (estimate-service regional outage), scenario file for faults and latency (`MOCK_MCP_SCENARIO` / `--scenario`); `python -m dr_agent.mock_mcp [--transport stdio|http]`.
- [x] Default `mcp-servers.json` (mock server over stdio) and `execution-policy.json` (the nine tools, risk classes, constraints on `region` and `snapshot`).
- [x] Proposer: `execution/proposer.py`, `llm/prompts/execution.py` (versioned, delimited escaped JSON), `llm/proposal_schema.py` (`ToolProposal`); `llm/parse.py` generalized to any schema. Wired into the planner and engine (`PROPOSED`, source `ai_proposed`, audit event `proposal`). `FakeProvider` tests: valid, schema-invalid then corrected, off-list tool, other server, invalid arguments, policy constraint, manual answer, model unavailable, injection attempt in step text, engine review flow.
- Exit: met. `tests/integration/test_execution_mcp.py` runs `estimate-service-executable.md` end to end against the mock server through the SDK's in-memory client, with the default policy: full failover (`COMPLETED`, 9 calls), an injected smoke-test failure followed by a two-person-approved rollback, an abort mid-call (step `UNKNOWN`, nothing runs afterwards), and restart recovery (`RUNNING` -> `UNKNOWN`, execution paused, the call is never re-sent). A stdio subprocess test and a manual streamable HTTP check also pass. Gate: 883 backend tests at 98.94%, lint and `mypy --strict` clean, 43 UI tests, audits clean. Decisions P10-1 to P10-9 in `scratchpad/phase-10/SUMMARY.md`.

### Phase 11: API, CLI, UI and delivery -- DONE 2026-09-24 (Docker run pending, as in Phase 7)
- [x] Re-verified Phases 0-10 first: lint clean, 883 backend tests (98.94%), 43 UI tests, no file over 200 lines.
- [x] `execution_runtime.py` (composition root shared by API and CLI: policy, `MCP_SERVERS_FILE`, SQLite store, restart recovery, MCP connections, dry-run executor built from the servers' catalog, optional proposer). The engine now routes dry runs to the dry-run executor and live runs to MCP.
- [x] `api/routes_execution.py`, `api/routes_steps.py` and `api/schemas_execution.py` (design section 8, plus `GET /execution/settings`); `api/execution_service.py` runs tool calls in background tasks after each decision and a slow ticker for approval timeouts; lifespan opens and closes the runtime in one task; error mapping (403/409/422/502 codes); CORS `PUT`; `poe gen-api` refreshed `openapi.json` and `schema.d.ts`.
- [x] `dr-agent execute --runbook --operator [--live]` (`cli_execute.py`, `cli_execute_steps.py`): Rich panel per step, prompts for approvers or decisions, refused answers asked again, steps blocked by a rolled-back dependency offered skip/close; exit codes 0 completed, 2 failed or aborted, 1 error.
- [x] UI (tabs later replaced by a section under the report, see the post-Phase-11 change below): Analyze / Execute tabs (no router), Execute view with settings-aware disabled state, name field with the "identity not verified" notice (remembered in `localStorage`), new-execution form (dry or live), executions list, execution header (mode badge, state, audit head, Start/Pause/Resume/Close/Abort with reason), steps by phase with step cards (call, verify and rollback calls with risk, source and approvals; results as text), call editor (JSON), audit panel with chain verification; hand-off from a finished report. Hooks `useExecution` (actions + polling), `useExecutionCatalog`, `useAudit`, `useStoredName`; vitest + RTL.
- [x] Docker: `mock-mcp` service (same image, streamable HTTP, `--allowed-host mock-mcp:*`, internal `tools` network, no published port, health check), `executions-data` volume on `/data`, config files baked into the API image, execution off unless `EXECUTION_ENABLED=true`. CI smoke test unchanged.
- [x] README, CLAUDE.md, `.env.example`, design doc, rules and summaries updated.
- Exit: **met except the Docker run.** Browser drill (Microsoft Edge driven by Playwright, `scratchpad/phase-11/browser_drill.py`; the Playwright MCP server was not connected in this session): dry run completed; live run against the mock server with the starter refused on a destructive step and two approvers accepted; injected smoke-test failure, two-person-approved rollback (DNS back to primary); abort; audit chain verifies for both runs (59 events on the live run). `ruff`, `mypy --strict`, 905 backend tests at 98.79%, 73 UI tests (97.7% lines, 85% branches), eslint/tsc/prettier, `pip-audit` and `npm audit` all clean. Docker is still not installed on this machine: the compose file was parsed and checked, the CI `docker` job remains the proof on first push. Decisions P11-1 to P11-10 in `scratchpad/phase-11/SUMMARY.md`.

### Post-Phase-11 change: execution follows the analysis -- 2026-09-24
Requested by the project owner: execution is not an independent step, and it lives under the analysis, not in its own tab. Confirmed scope: enforce this in the server and the UI.
- [x] API: `POST /executions` takes `analysisJobId` (a succeeded analysis job) instead of runbook text; the execution uses that job's parsed runbook and follows its execution plan (`execution/analysis_link.py`); `Execution.analysis` and the `execution_created` audit event record the analysis. Analysis jobs keep their parsed runbook (server side only).
- [x] CLI: `dr-agent execute` analyzes first (optional `--inventory`), shows risk, RTO, gaps and plan, and asks; it refuses before analyzing when execution is disabled.
- [x] UI: Execute tab removed; `ExecutionSection` under the finished report (risk warning, runs of this analysis); `poe gen-api` refreshed the client.
- [x] Gate: 911 backend tests (98.79%), 73 UI tests, lint clean; the browser drill (now starting from an analysis) passes. Details in `scratchpad/phase-11/SUMMARY.md` (section "Follow-up") and design section 17.

## History and knowledge-base phases
Design: [`docs/design/analysis-history.md`](design/analysis-history.md). Decisions: ADRs 0007-0009.
Decision log (2026-09-25, confirmed with the project owner): store every finished analysis with its raw runbook Markdown, linked to the executions created from it; build a knowledge base from that history for future analyses and recovery; only facts measured by code may reach LLM prompts, never past model text or tool output; design first, then build.

### Phase 12: History and knowledge-base design (documents only) -- DONE 2026-09-25 (approved)
- [x] Design doc: context, goals and non-goals, architecture, data model and migrations, saving and retention, API, CLI, UI, knowledge-base facts, step matching, uses, configuration, security notes, later work, testing strategy.
- [x] ADRs 0007 (persist analyses, linked to executions), 0008 (store raw runbook Markdown), 0009 (knowledge base from measured facts only), all Proposed; ADR index updated.
- [x] README roadmap updated; summary in `scratchpad/phase-12/SUMMARY.md`.
- [x] Exit: the project owner approved the design and ADRs 0007-0009 on 2026-09-25; they are Accepted and ADR 0004 is marked partly superseded.

### Phase 13: Analysis history -- DONE 2026-09-25 (Docker run pending, as in Phase 7)
- [x] Re-verified Phases 0-12 first: lint clean, 911 backend tests, 78 UI tests (after `uv sync --reinstall` fixed the venv launchers).
- [x] `storage/` (shared connection helper, numbered migrations; migration 2 adds `analyses` and `executions.analysis_id`); `execution/sqlite_store.py` moved onto it, and writes `analysis_id` only when that analysis is stored.
- [x] `history/` (`AnalysisRecord`, `AnalysisStore` protocol, SQLite store, service with save/retention/staleness); `JobStore` `on_success` hook (saved before the job is marked succeeded, `historySaved` on the job); CLI saves by default (`--no-save`); `HISTORY_ENABLED`, `DB_PATH` (fallback `EXECUTION_DB_PATH`), `HISTORY_RETENTION_DAYS`, `HISTORY_STALE_AFTER_HOURS`; analysis prompt `PROMPT_VERSION = "analysis/1"`.
- [x] API `routes_history.py` (list with filters and keyset pages, detail with provenance and `stale`, runbook as `text/plain` download, HTML report, executions, delete with `409` while executions exist); job poll, job HTML export and `POST /executions` fall back to the store (`api/analysis_lookup.py`); `HISTORY_DISABLED` (403); `poe gen-api`.
- [x] CLI `history list|show|delete` (`cli_history.py`), `execute --analysis ID` with a stale warning; shared `cli_common.py` and `cli_analysis.py` keep `cli.py` under 200 lines.
- [x] UI History tab (`components/history/`: filters, table, load more, detail with runbook download, stale banner and the shared `ExecuteRunbook` section); "Saved to history" note under a new report; hooks `useHistory`, `useStoredAnalysis`.
- [x] Docker (`DB_PATH=/data/dr-agent.db` on the `dr-agent-data` volume, `HISTORY_*` passed through), `.gitignore` / `.dockerignore` `*.db`, `.env.example`, README (features, layout, dashboard, CLI, API, new "Analysis history" section, configuration, security notes), CLAUDE.md, rules, design section 13.
- Exit: **met except the Docker run.** Restart tests (API: analyze, new app on the same file, poll, export and execute; CLI: `execute --analysis`); a version-1 database migrates with its executions intact; golden report unchanged; browser drill (Playwright MCP): analyze a sample -> "Saved to history" -> API restarted on the same file -> History tab lists it -> open -> dry run created from the stored analysis -> run count 1. Gate: ruff, `mypy --strict`, 960 backend tests at 98.84%, 90 UI tests (96.99% lines), eslint/tsc/prettier, `pip-audit` and `npm audit` clean; every file under its size limit. Docker is still not installed on this machine; the compose change is checked by the CI `docker` job on first push. Decisions P13-1 to P13-10 in `scratchpad/phase-13/SUMMARY.md`.

### Phase 14: Knowledge base -- DONE 2026-09-25
- [x] Re-verified Phases 0-13 first: lint clean, 960 backend tests (98.84%), 90 UI tests, audits clean, CLI smoke run with history.
- [x] `models/insights.py` (`ServiceHistory`, `StepHistory`, `ExecutionOutcome`, `DependencyTrend`); `knowledge/`: step fingerprints, durations from audit events (active and elapsed minutes, execution window), facts from stored analyses and finished **live** runs (dry runs only counted), `for_runbook()` matching, history rules (`GapType.HISTORICAL`: failed or rolled back >= 50% of >= 2 runs; median above estimate x1.5; median completed run above the RTO; dependency down or unreachable in >= 50% of >= 3 analyses), SQLite source, `KnowledgeBase` (a storage error never fails an analysis).
- [x] Analyzer: HISTORICAL gaps join the rule gaps (rule score, rule-owned so the model cannot add them); `<history>` prompt block from an explicit allow-list (`knowledge/prompt_facts.py`, test-enforced), escaped like the other blocks; `PROMPT_VERSION` `analysis/2`; system prompt names `<history>` as untrusted data; `.claude/rules/llm-and-security.md` exception added. `historicalInsights` on the report, left out of the JSON when empty.
- [x] Terminal and HTML reports show the history; `GET /api/v1/services/{name}/history`; CLI `execute` prints the history line and "Previous live runs" per step panel; UI "Historical insights" section and the same line on execution step cards.
- [x] `KNOWLEDGE_ENABLED`, `KNOWLEDGE_MAX_RUNS`, `KNOWLEDGE_MAX_ANALYSES`, `KNOWLEDGE_IN_PROMPT`; `.env.example`, compose, README, CLAUDE.md, rules, design section 14.
- Exit: **met.** `tests/integration/test_knowledge_mcp.py`: two live runs against the mock MCP server with a failing smoke test that is rolled back, then the next analysis reports "Step 5 failed or was rolled back in 2 of 2 past live runs." and its prompt carries the counts but not the operator's close reason. Golden report unchanged; second golden `mock-data/expected-reports/estimate-service-history.json` from `backend/tests/fixtures/history/estimate-service.json`; threshold tests for each rule. Gate: ruff, `mypy --strict`, 1003 backend tests at 98.92%, 94 UI tests (97.06% lines), eslint/tsc/prettier, `pip-audit` and `npm audit` clean; every file under its size limit. Decisions P14-1 to P14-10 in `scratchpad/phase-14/SUMMARY.md`.

### Post-Phase-14 change: read-only history, live-run button -- 2026-09-25
Requested by the project owner after trying the dashboard.
- [x] History tab no longer offers "Execute this runbook…"; an opened analysis shows "Executions of this analysis" (runs, then a chosen run's steps and verified audit log, read-only). New endpoint `GET /api/v1/analyses/{id}/executions/{executionId}`; `usePastExecutions`, `PastExecutions`; `ExecutionHeader` takes an optional tool-call limit.
- [x] "Create live run": the rule was already "enabled until a live run of this analysis completes"; it was disabled only because the server ran without `EXECUTION_ALLOW_LIVE=true`. Tests now pin the rule (failed or aborted live runs keep it enabled, a completed one disables it).
- [x] Progress feedback: pending execution requests show a `ProgressNote` (what the server is doing, elapsed seconds; for run creation, why it can take minutes), and a "Run in progress" note while tool calls run in the background (`callingTools`).
- [x] Step buttons of a new run: already enabled once the run is created (manual steps can be marked done or skipped before Start). The reported disabled state was the ~10-minute creation of an order-service live run (AI proposals for 6 unannotated steps on the local model), now explained by the progress note; an empty "Your name" now also shows why the step buttons are disabled. Tests: `ManualSteps.test.tsx`.
- [x] Creating a run clears the run on screen first, so a finished live run's steps no longer stay visible while a new dry run is being created.
- [x] UI redesign (owner request: "looks simple and AI generated"): theme tokens and utilities, command-bar header with server status, journey steps, input that folds away after a report, verdict hero with key-figure tiles and section jumps, execution option cards, run progress bar, sticky run controls, step timeline, readable audit log, polished history. No new dependencies; accessible names unchanged.
- [x] Gate and browser check: see `scratchpad/phase-14/SUMMARY.md` ("Follow-up").

## Verification
(Phase 5 CLI/API checks below were run on 2026-09-23 -- see `scratchpad/phase-5/SUMMARY.md`; the UI check was run on 2026-09-23 -- see `scratchpad/phase-6/SUMMARY.md`. All passed except the first CLI line: the exit-2 logic is correct and tested, but live models scored auth-service + major-outage at 75 (7B) / 50 (3B) and the rule fallback at 80, so it exited 0. Open decision recorded in that summary.)
- `uv run poe test` (backend + frontend) passes with coverage >80%; `mypy --strict` and ruff clean.
- CLI: `dr-agent analyze --runbook mock-data/runbooks/auth-service.md --inventory mock-data/inventories/major-outage.json` exits 2 with critical risk; estimate-service + healthy inventory exits 0.
- API: `curl` multipart and JSON analyze, 422/400 error shapes, health endpoint.
- UI: load each mock runbook in browser and confirm all report sections render.
- Make the LLM unreachable (stop Ollama, or use a wrong `LLM_API_KEY`) and confirm graceful-degradation output.
- Execution (Phase 11, run 2026-09-24): `scratchpad/phase-11/browser_drill.py` in a browser (dry run, live run with two approvers, injected failure and rollback, abort, audit chain verifies) and `dr-agent execute` against the mock server over stdio.
- History (Phase 13, run 2026-09-25): browser drill with an API restart (analyze, saved, restart, History tab, dry run from the stored analysis); `dr-agent analyze` + `history list`.
- Knowledge base (Phase 14, run 2026-09-25): `test_knowledge_mcp.py` (live runs change the next analysis) and repeated `dr-agent analyze` runs showing "Historical insights".

## Questions and suggestions (please review; defaults assumed if unanswered)
1. **LLM**: Claude is not open source, so default is Ollama + Qwen2.5 14B (or Llama 3.1 8B on low RAM). Available hardware (RAM/GPU)? Small models give weaker reasoning, hence the hybrid deterministic + LLM design. Is that acceptable, or is Claude allowed as an optional provider behind the same interface?
2. **CLI kept?** Assumed yes (brief lists SREs via CLI as primary users), alongside the API and React UI.
3. **React scope**: assumed a dashboard for a single analysis, no login, no persistence. Do you want history/trend storage (SQLite) for "continuous readiness"? Suggest deferring to a later phase. *(Resolved 2026-09-25: analysis history in Phase 13, knowledge base in Phase 14.)*
4. **Deployment**: assumed Docker Compose + GitHub Actions. Is Docker available on your machine (Windows 11)? Otherwise a Makefile/PowerShell local-run path is provided.
5. **Brief inconsistencies I will resolve as noted**: `dependsOn` is "inferred by AI" but lives in the parsed model; inventory needs a mock status field; "Never say looks good" prompt rule conflicts slightly with honest scoring, so I keep it but require evidence-backed findings; GET analyze with file paths is a path-traversal risk, so restricted to an allow-listed folder.
6. **Parser edge cases anticipated**: mixed time units, ranges ("10-15 min"), nested lists, tables instead of lists, owners as `@handle` or "team", steps without numbers, non-English headings. Should tables be supported in v1? Suggest yes for steps.
7. **Extras (optional)**: multi-runbook batch analysis, OpenTelemetry metrics, PDF export. Suggest skipping for the PoC.
