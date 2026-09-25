# Phase 11 summary: execution API, CLI, UI and delivery

Date: 2026-09-24. Status: done. All exit criteria met except running Docker, which is not installed on this machine (same as Phase 7).

## Goal
Make runbook execution usable: an HTTP API (design section 8), `dr-agent execute`, the dashboard's Execute tab, and Docker delivery with the mock MCP server, while execution stays off unless an operator enables it.

## Before starting: re-verification of Phases 0-10
- `ruff check`, `ruff format --check`, `mypy --strict` (105 files) clean; 883 backend tests at 98.94%; UI eslint/tsc/prettier clean, 43 vitest tests; no file over the size limits.

## Produced
Backend
- `execution_runtime.py`: the composition root for execution, shared by the API lifespan and the CLI. It loads the policy and `MCP_SERVERS_FILE`, opens the SQLite store, runs restart recovery, connects the MCP servers (owner task), builds a `DryRunExecutor` from their tool catalog, and adds the proposer when `EXECUTION_AI_PROPOSALS` is on and an LLM is configured.
- Engine: optional `dry_run_executor`; `StepRunner` picks the executor by the execution's mode. The call bookkeeping helpers moved to `execution/call_records.py` (the runner was 208 lines).
- API: `schemas_execution.py`, `routes_execution.py` (settings, tools, create, list, get, lifecycle, audit), `routes_steps.py` (call edit/accept, approve, reject/skip/manual/mark-done/verify/retry/rollback), and `execution_service.py` (background `advance()` after decisions, a 15 s ticker, shutdown). The lifespan opens the runtime only with `EXECUTION_ENABLED=true`. `AppState.execution`; CORS allows `PUT`; `ChainVerification` is now camelCase; `api/body.safe_label` is public.
- CLI: `dr-agent execute --runbook --operator [--live]`. `cli_execute.py` holds the session loop and `cli_execute_steps.py` the per-step prompts and panels.
- Settings: `EXECUTION_AI_PROPOSALS` (default `true`). Mock server: `--allowed-host` (DNS-rebinding protection for the HTTP transport).
- OpenAPI: `frontend/openapi.json` and `src/api/schema.d.ts` regenerated with `poe gen-api` (the drift test passes).

Frontend
- `api/http.ts` (shared request plumbing), `api/executionClient.ts` (merged into `createApi`), and execution type aliases in `api/types.ts`.
- Hooks: `useExecution` (actions + polling while RUNNING), `useExecutionCatalog` (settings + list), `useAudit`, `useStoredName`.
- Components: `AnalyzeView` (the former App body plus an "Execute this runbook…" hand-off), `ExecuteView`, and `execution/`: `NewExecutionForm`, `ExecutionList`, `ExecutionPanel`, `ExecutionHeader`, `StepCard`, `StepActions`, `CallView`, `CallEditor`, `AuditPanel`, `handlers.ts`. `App` has Analyze / Execute tabs (no router). `ErrorPanel` takes a `title`. `lib/executionLabels.ts` holds tones with icons and text, so color is never the only signal.
- Tests: `executionClient.test.ts`, `hooks/executionHooks.test.ts`, `components/execution/execution.test.tsx`, `panels.test.tsx`, `components/ExecuteView.test.tsx`, and fixtures in `test/executionFixtures.ts`.

Docker
- `docker-compose.yml`: a `mock-mcp` service (the API image running `python -m dr_agent.mock_mcp --transport http --host 0.0.0.0 --port 8765 --allowed-host mock-mcp:*`, hardened like the others, TCP health check), an internal `tools` network (no route out) shared with `api` only, an `executions-data` volume on `/data`, and execution env vars defaulting to off.
- `docker/api.Dockerfile`: `/data` owned by the app user; `execution-policy.json` and `docker/mcp-servers.json` (`http://mock-mcp:8765/mcp`) under `/app/config`; `EXECUTION_DB_PATH`, `EXECUTION_POLICY_FILE` and `MCP_SERVERS_FILE` set.
- CI: unchanged. Its smoke test still starts `api ui --no-deps` with execution off.

Documentation: README (status, What it does, Stack, architecture and deployment diagrams, layout, Docker, the execution drill in the demo walkthrough, Dashboard, CLI, REST API, Runbook execution, configuration, roadmap, security notes); `docs/IMPLEMENTATION_PLAN.md` (Phase 11 and Verification); `docs/design/runbook-execution.md` (section 17, Phase 11 notes); CLAUDE.md; `.claude/rules/python-backend.md`, `testing.md` and `frontend-react.md`; `.claude/commands/demo.md`; `.claude/skills/phase-workflow`; `.env.example`.

## Decisions and deviations
- P11-1 **`POST /executions` takes JSON only**, not multipart as design section 8 suggested. The dashboard sends text, and the CLI calls the engine directly.
- P11-2 **Extra endpoint `GET /execution/settings`.** It answers while execution is off, so the UI can explain why, and it carries `approvalsByRisk`, so the UI does not duplicate the approval rule.
- P11-3 **Action routes are grouped**: `POST /executions/{id}/{action}` and `POST .../steps/{n}/{action}`, with the allowed action names typed in OpenAPI and the generated client.
- P11-4 **Tool calls run in background tasks, never in a request, except `rollback`.** A rollback runs within its request so its outcome comes back directly; it is bounded by the tool timeout. A 15 s ticker advances running executions so approval timeouts fire without traffic. Background work cut off at shutdown is handled by restart recovery.
- P11-5 **Dry runs check against the real schemas.** The dry-run executor is built from the connected servers' tool listing, and the engine chooses the executor by mode. A dry run therefore still needs the MCP servers reachable at startup, but it never calls a tool.
- P11-6 **New setting `EXECUTION_AI_PROPOSALS`** (default `true`). Proposals are requested while an execution is created, one model call per unannotated step, which takes minutes with a local CPU model; this lets operators turn them off.
- P11-7 **The mock server over HTTP keeps DNS-rebinding protection** through `--allowed-host`. With `--host 0.0.0.0` the SDK would otherwise disable it. It sits on an internal network with no published port. Checked by hand: a foreign Host header gets HTTP 400.
- P11-8 **The CLI resumes a paused execution automatically** once the operator has made a decision, printing the pause reason. An approved step blocked by a rolled-back dependency is offered skip / close / abort instead of leaving the session with nothing to do.
- P11-9 **UI conventions.** The approver name is remembered per browser (convenience only), next to an "identity not verified" notice. Each step card has one reason field. Batch approval of a phase's read-only steps (ADR 0003) is not built; one click per step proved enough.
- P11-10 **The browser drill ran with Playwright for Python driving the installed Microsoft Edge** (`uv run --with playwright`, not a project dependency). The Playwright MCP server named in the plan was not connected in this session.

## Found and fixed during the phase
- The execution list kept a stale state badge ("Created" for a run already paused), because it was refreshed only on create. It now refreshes whenever the viewed execution changes state (seen in the first drill screenshots, fixed, drill re-run).
- Size limits: `runner.py` (208 lines after the executor change) was split into `call_records.py`, `execution.test.tsx` (206) into `panels.test.tsx`, and `StepActions.tsx` (154, over the 150-line component limit) was reduced with a small `Action` component.

## Evidence
- Browser drill (`scratchpad/phase-11/browser_drill.py`, screenshots in `results/`). Setup: mock server over HTTP with `smoke-fails-once.json`, API with both switches on and a fresh DB, Vite UI.
  1. `1-dry-run-completed.png`: dry run, all 5 steps approved (Ann; Ben as the second approver on steps 3 and 5), started, step 1 confirmed by hand; `COMPLETED` with simulated results and no call to the server.
  2. `2-starter-cannot-approve-destructive.png`: live run; Olivia, who started it, is refused on step 3 (`POLICY_VIOLATION`).
  3. `3-live-two-approvers.png`: step 3 shows "Approvals 2/2 (Ann, Ben)".
  4. `4-live-injected-failure.png`: steps 1-4 succeed against the mock server; step 5's smoke test fails ("checkout returns HTTP 500"), and the execution is paused ("Paused: step 5 failed").
  5. `5-live-rolled-back.png`: rollback approved by Ann and Ben (destructive), `Roll back`; the step is `ROLLED_BACK` and the DNS result shows primary again.
  6. `6-aborted-audit-verified.png`: aborted with a reason; the audit log reports "Hash chain verified: 59 events". The API confirmed a valid audit chain for both executions.
- API integration tests (`test_api_execution.py`, `test_api_execution_steps.py`), with the in-process mock server and `settle()` for background work, cover:
  - execution disabled by default;
  - the tools list with risks;
  - a full live run, and a dry run that never calls the server;
  - the live switch;
  - approval errors (stale hash 409, starter 422, bad hash 422), 404s, a wrong-state 409 and a parse error;
  - failure with a two-person rollback, retry, reject/manual/mark-done/skip, call edits (including an off-list tool, 422), and abort.
- CLI tests:
  - `test_cli_execute_session.py`, with scripted answers and an in-memory engine: happy path, re-asking after refused answers, failure with rollback and then a blocked step closed, abort, reject/manual/retry, skip;
  - `test_cli_execute.py`, through `CliRunner` with the real stdio mock server: live run exits 0 with a valid audit chain, abort exits 2, execution disabled exits 1.
- Gate:
  - backend: `ruff check` and `ruff format --check` clean (196 files), `mypy --strict` clean (113 source files), 905 tests at 98.79% coverage;
  - frontend: eslint/tsc/prettier clean, 73 vitest tests (97.7% lines, 85.4% branches), production build succeeds;
  - `pip-audit`: no known vulnerabilities; `npm audit`: 0;
  - every Python file under 200 lines and every component under 150.
- Docker: not installed here. `docker-compose.yml` was parsed (services `api`, `ui`, `mock-mcp`; `mock-mcp` only on the internal `tools` network with no ports; the volume is mounted; execution defaults off). The CI `docker` job remains the proof on first push; it builds the image `mock-mcp` also uses.

## Environment note
The uv launcher problem (`uv trampoline failed to canonicalize script path`) is still present, so the gate ran through `python -m`. The Playwright MCP server stayed disconnected.

## Open items after Phase 11 (outside the plan)
- Run `docker compose up` with `EXECUTION_ENABLED=true` on a Docker host (or let CI run), and consider a CI step for the execution path.
- OIDC for approvers, batch approval of read-only steps, and server-sent events instead of polling (design section 16).

## Follow-up (2026-09-24): execution follows the analysis
Requested by the project owner after reviewing Phase 11: execution must not be an independent step, and it belongs under the analysis rather than in its own tab. The owner chose to enforce this in the server as well as the UI.

Changed
- `execution/analysis_link.py`: `analysis_ref()` (job id, risk score and level, AI availability, analysis time) and `phase_edges()` (each report phase waits for the whole previous phase, so the planner reproduces the report's phases, AI-inferred order included). `Execution.analysis` is optional, so executions stored earlier still load. The planner and engine accept `analysis`, and the `execution_created` audit event records it.
- API: analysis jobs keep their parsed runbook and label (server side only). `CreateExecutionRequest` is now `{analysisJobId, mode, startedBy}`: `404` for an unknown job, `409 CONFLICT` while the analysis is unfinished or failed, `422` for the old runbook-text body. `ExecutionSummary.analysisJobId`.
- CLI: `dr-agent execute` checks the switches, analyzes (optional `--inventory`), prints a one-line readiness summary and asks `Execute this runbook now?`. Declining exits 0 and executes nothing.
- UI: the tabs and `ExecuteView` are gone. `AnalyzeView` shows "Execute this runbook…" under a finished report, which opens `ExecutionSection` (name field, a risk warning for HIGH or CRITICAL, dry or live run from the analysis job, runs of this analysis, the execution panel). `NewExecutionForm` no longer takes runbook text.
- Tests: API (`analyze()` helper, unfinished/unknown analysis, analysis recorded and phases matching the report), CLI (confirmation, decline, disabled before analysis), unit (`test_execution_analysis_link.py`), UI (`ExecutionSection.test.tsx` replaces `ExecuteView.test.tsx`).
- Browser drill updated to start from an analysis. It passed with a new screenshot, `0-report-then-execute.png`.

Found while doing it
- With execution disabled, `dr-agent execute` used to run the whole analysis before refusing. It now refuses first.

Limit: analysis jobs are in memory, so after an API restart an execution needs a fresh analysis. Executions already created persist as before.

Evidence: 911 backend tests at 98.79%, 73 UI tests (97.8% lines, 86.8% branches), ruff, mypy and eslint/tsc/prettier clean; drill passed (dry run completed; live run aborted after rollback; both audit chains valid).

## Follow-up 2 (2026-09-24): run controls
Requested by the project owner.
- The run controls moved out of the execution header into `ExecutionControls` below the last step.
- **Start run** is enabled only when no step is waiting for approval or review (`PLANNED`, `PROPOSED`, `AWAITING_APPROVAL`, `REJECTED`); manual and skipped steps need none. A hint lists the steps still waiting.
- **Abort run** is enabled only once the run has started (`RUNNING` or `PAUSED`). Pause, Resume and Close appear only when they apply, and a finished run shows its final state instead of buttons.
- **Create dry run** and **Create live run** are disabled once a run of that mode has completed for this analysis.
- UI only. The API and CLI still allow approving ahead of or during a run, and aborting before the start, as the design allows.
- Evidence: 78 UI tests pass; lint clean; the browser drill (updated for the new button names and states) passed again.
