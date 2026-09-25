# DR Readiness Agent

An AI-powered Disaster Recovery (DR) readiness tool. It reads Markdown DR runbooks, extracts the recovery steps, checks their dependencies against a system health inventory, and produces a readiness report with a risk score, RTO feasibility, single points of failure, gaps and an execution plan.

The whole stack is open source. Analysis runs on either a local LLM through Ollama (no data leaves your machine) or any OpenAI-compatible API such as OpenAI or Mistral, selected by configuration. Docker Compose uses the hosted API only.

> **Status:** proof of concept. The readiness analysis (Phases 0-7) is complete: decisions and spike, foundation, Markdown parser, health validator, LLM analysis, report formatters, CLI, REST API, React dashboard, and Docker/CI/security hardening. The Docker setup is written and a CI job is set up to build and smoke-test it, but it has not run anywhere yet (no Docker on the development machine, and CI has not run); see [Phase 7](scratchpad/phase-7/SUMMARY.md).
>
> Human-authorized runbook execution (Phases 8-11) is complete too: design and ADRs, execution core, MCP integration with a bundled mock MCP server, and the API, `dr-agent execute`, execution in the dashboard and a `mock-mcp` Compose service. Execution always follows a readiness analysis: it is started from the finished report and follows its execution plan. It is off by default; see [Runbook execution](#runbook-execution). The browser drill ran in Microsoft Edge (Playwright); the new Compose service is, like the rest of the Docker setup, not yet run on a real Docker host ([Phase 11](scratchpad/phase-11/SUMMARY.md)).

## Why

DR runbooks are written by hand, rarely validated, never cross-checked against live systems, and their RTO targets are usually aspirational. This tool gives SREs, engineering managers and compliance teams a repeatable readiness check instead of a once-a-year exercise.

## What it does

- **Parse** any Markdown runbook into structured data: service, owner, RTO, RPO, dependencies and ordered steps with owners and time estimates.
- **Validate** dependencies against a health inventory (mocked in this PoC, swappable for live checks).
- **Analyze** with a local LLM: dependency chains, RTO feasibility, single points of failure, gaps, and a 0-100 risk score. Deterministic facts (RTO math, dependency health, four rule-checkable gap types, execution phases) are computed in code; the LLM adds reasoning on top and the report degrades gracefully to rule-based results if the model is unavailable.
- **Report** as JSON, colored terminal output (Rich) or HTML (Jinja2, autoescaped), from a CLI (`dr-agent`), a REST API (FastAPI) or a React dashboard (risk gauge, RTO waterfall, dependency table, filterable gaps, JSON/HTML export).
- **Keep history**: every finished analysis is stored with its runbook text, inventory and how it was produced, linked to the executions created from it. Past reports can be listed, reopened, exported and executed again after a restart (dashboard History tab, `dr-agent history`, `/api/v1/analyses`). See [Analysis history](#analysis-history).
- **Learn from past runs**: new analyses use what earlier analyses and live runs of the same service measured (step outcomes and times, end-to-end time against the RTO, dependencies that kept failing). This adds HISTORICAL gaps and a "Historical insights" section, and shows "previous live runs" on each execution step. Only numbers computed by code reach the model. See [Knowledge base](#knowledge-base).
- **Execute** (opt-in, after an analysis): from under the finished report, the API or `dr-agent execute`, carry out the analyzed runbook's execution plan whose [MCP](https://modelcontextprotocol.io/) tool calls run only after named people approve them. Calls come from `Tool:` annotations or are AI-proposed and reviewed. Runs include verification, rollback, abort, a tamper-evident audit log and restart recovery, against a bundled mock MCP server that simulates a DR environment. See [Runbook execution](#runbook-execution).

## Stack

| Area | Choice |
|---|---|
| Backend | Python 3.12, FastAPI + Uvicorn, Pydantic v2, Typer, Rich, Jinja2, markdown-it-py, httpx, structlog; execution: official MCP Python SDK (`mcp`), jsonschema, SQLite (standard library) |
| LLM | Swappable `LLMProvider` interface (see [Phase 4 findings](scratchpad/phase-4/SUMMARY.md)): Ollama with `qwen2.5:7b-instruct` locally (see [Phase 0 findings](scratchpad/phase-0/SUMMARY.md)), or any OpenAI-compatible `/chat/completions` API (OpenAI, Mistral, vLLM, ...) with an API key, over plain httpx with no vendor SDK |
| Frontend | React 18, TypeScript, Vite, Tailwind, Recharts, openapi-typescript + openapi-fetch (typed client generated from the API schema) |
| Quality | uv, ruff, mypy strict, pytest, vitest + React Testing Library, eslint, prettier |
| Delivery | Docker Compose (api, ui on nginx, mock-mcp on an internal network; the LLM is a hosted OpenAI-compatible API), GitHub Actions (quality, audit, Docker smoke test) |
| Security | pip-audit, npm audit, CSP and hardening headers, prompt-delimiter escaping |

## Architecture

Everything in the diagram is built. The dashboard talks to the API through a client generated from its OpenAPI schema. The CLI and the API both call the same framework-free service functions in `service.py` (`parse_markdown()`, then `analyze_runbook()`); `wiring.py` is the single place that picks the concrete LLM provider and health checker from configuration.

```
            +-------------+     +---------------------+
 runbook.md |             |     |   React dashboard   |
 ---------> |  CLI (Typer)|     +----------+----------+
 inventory  |             |                | HTTP
            +------+------+     +----------v----------+
                   |            |   FastAPI service   |
                   |            +----------+----------+
                   +-----------+-----------+
                               |  service.py: parse_markdown() + analyze_runbook()
        +----------------------+-----------------------+
        |                      |                       |
 +------v-------+      +-------v--------+      +-------v--------+
 |   Parser     |      |   Validator    |      |    Analyzer    |
 | markdown-it  |      | HealthChecker  |      |  LLMProvider   |
 +--------------+      | Mock | Live    |      | Ollama         |
                       +----------------+      | OpenAI-compat. |
                                               | Disabled, Fake |
                                               +----------------+
```

Rules that keep it swappable: core modules import no web or CLI framework, and the health checker and LLM provider are injected.

The execution side (Phases 9-11) sits beside the analysis pipeline and follows the same rules. An execution is always created from a finished analysis: it takes that analysis's parsed runbook, follows its execution plan (each phase waits for the whole previous one, which reproduces the report's phases, AI-inferred order included) and records the analysis job id and risk score. `execution_runtime.py` is its composition root, shared by the API lifespan and `dr-agent execute`: it loads the policy and `MCP_SERVERS_FILE`, opens the store, runs restart recovery and connects to the MCP servers. The API runs tool calls in background tasks after each decision and the dashboard polls, as it does for analysis jobs:

```
 runbook --> parser (Tool: / Verify-Tool: / Rollback-Tool:)
                |
                +-- steps without annotation --> execution/proposer --> LLMProvider
                |                                (allow-listed tools only, validated,
                v                                 always reviewed by a person)
 execution/planner --> Execution (one StepRun per step, phases as in the report)
                |
 human decisions --> execution/engine --> ToolExecutor (injected)
 (approve, edit,       |        |          DryRunExecutor | FakeExecutor | McpToolExecutor
  skip, abort ...)     |        v                                          |  MCP SDK: stdio,
                       |   policy + approvals checked again                |  streamable HTTP,
                       |   right before every call                         v  in-memory (tests)
                       v                                          mock_mcp: drsim server,
             ExecutionStore (SQLite): state +                     simulated DR environment
             hash-chained audit events, one transaction
```

### Deployment (Docker Compose)

```
 browser -- http://localhost:8080 --> +----------------------------+
                                      |  ui  (nginx, unprivileged) |  static React build + CSP
                                      |  /api/* proxied -------+   |
                                      +------------------------|---+
 curl, /docs -- http://localhost:8000 --------------+          |
                                                    v          v
                                      +----------------------------+
                                      |  api (FastAPI, non-root,   |  mock-data baked in
                                      |  read-only filesystem)     |  (API_ALLOWED_DIR)
                                      +------+-------------+-------+
                    dr-agent-data volume    |             |  internal network "tools"
                    (/data/dr-agent.db) ----+             |  (no route out, no published port)
                                                          v
                                            +---------------------------+
                                            | mock-mcp (same image, MCP |  streamable HTTP :8765,
                                            | server, simulated DR env) |  Host must be mock-mcp:*
                                            +---------------------------+
                                                    | api -> HTTPS + LLM_API_KEY (bearer)
                                      +-------------v--------------+
                                      |  hosted OpenAI-compatible  |  e.g. api.mistral.ai/v1,
                                      |  API (outside compose)     |  api.openai.com/v1
                                      +----------------------------+
```

No model runs inside compose. The `api` container refuses to start without `LLM_API_KEY` (unless `LLM_PROVIDER=none`), and `ui` starts once `api` is healthy. Both published ports are bound to `127.0.0.1` only. `mock-mcp` has no published port and sits on an internal-only network with `api`; execution stays off unless `EXECUTION_ENABLED=true`.

## Repository layout

```
AI-Powered Disaster.md      original brief (Node/Claude version, read-only)
docs/IMPLEMENTATION_PLAN.md phased plan and open questions
docs/design/                runbook-execution.md: design of human-authorized execution via MCP
docs/adr/                   architecture decision records 0001-0006 (execution)
scratchpad/                 spikes and per-phase summaries
  phase-0/                  model spike, results and summary
  phase-1/                  foundation summary and decisions
  phase-2/                  parser summary and decisions
  phase-3/                  health validator summary and decisions
  phase-4/                  LLM analysis + formatters summary, live-model verification and results
  phase-5/                  CLI + REST API summary, live-model verification and results
  phase-6/                  React dashboard summary and browser screenshots
  phase-7/                  hardening and delivery summary, security review, verification evidence
  phase-8/                  execution design summary (design doc + ADRs, approved)
  phase-9/                  execution core summary, decisions P9-1 to P9-10, evidence
  phase-10/                 MCP integration summary, decisions P10-1 to P10-9, evidence
  phase-11/                 execution API/CLI/UI/Docker summary, browser drill script and screenshots
CLAUDE.md, .claude/         Claude Code rules, commands, skills, hooks
.mcp.json                   MCP servers (context7, playwright)
pyproject.toml, uv.lock     Python project, tools and poe tasks
.env.example                configuration template (copy to .env)
mcp-servers.json            MCP servers the executor may reach (default: the bundled mock, stdio)
execution-policy.json       allow-listed tools, risk classes and argument constraints
.github/workflows/ci.yml    CI: quality (lint, tests, UI build), audit (pip-audit, npm audit), Docker
                             build + rule-based smoke test through the UI proxy
docker-compose.yml          api, ui, mock-mcp (hardened: read-only, no capabilities), dr-agent-data
                             volume, internal tools network; LLM is a hosted API
.dockerignore               keeps tests, caches, .env and scratchpad out of build contexts
docker/                     api.Dockerfile, ui.Dockerfile (multi-stage), nginx.conf (proxy + CSP),
                             mcp-servers.json (the mock-mcp service, used inside the api image)
backend/src/dr_agent/
  config.py                 validated settings (fail fast)
  service.py                parse_markdown() / analyze_runbook() / validate_inventory(): the one
                             pipeline the CLI and API share (framework-free)
  loaders.py                files, uploads and JSON -> validated models or typed errors
  wiring.py                 composition root: settings -> LLMProvider + HealthChecker
  execution_runtime.py      composition root for execution: policy, MCP servers, store, recovery
  cli.py, cli_output.py     Typer CLI (`dr-agent`); `cli_common.py` startup and error exits
  cli_analysis.py           run + store an analysis, or load a stored one (analyze, execute)
  cli_history.py            `dr-agent history list|show|delete`
  cli_execute*.py           `dr-agent execute`: session loop and per-step prompts
  models/                   runbook, inventory, report, insights (Pydantic v2)
  storage/                  the shared SQLite file: connection helper, numbered migrations
  knowledge/                knowledge base (framework-free): step fingerprints, durations from audit
                             events, facts, HISTORICAL rules, prompt allow-list, SQLite source
  history/                  stored analyses (framework-free): records, `AnalysisStore` protocol,
                             SQLite store, service (saving, retention, staleness)
  utils/                    errors, structlog logging, timing
  core/                     markdown parser (incl. tool-call annotations); RTO/execution-plan/gap
                             rules, shared dependency graph, and the LLM+rules analyzer, `run_analysis()`
  health/                   health checkers (mock, live) + dependency cross-match
  llm/                      `LLMProvider` protocol, Ollama / OpenAI-compatible / disabled / fake
                             implementations, shared retry backoff, prompts (analysis, tool-call
                             proposals), response parsing/validation for any schema
  formatters/               JSON, Rich terminal and Jinja2 HTML report formatters, health table
                             (kept outside `core/` since `core/` may not import Rich)
  api/                      FastAPI app factory, routes (analysis, jobs, HTML export, samples), job
                             store, body reader, path allow-list, error handlers, request-id
                             middleware (`python -m dr_agent.api`), OpenAPI export for the UI client;
                             execution routes (`routes_execution.py`, `routes_steps.py`), schemas and
                             the background advancing service (`execution_service.py`); history
                             routes (`routes_history.py`) and the memory-then-history lookup
                             (`analysis_lookup.py`)
  execution/                runbook execution (Phases 9-10, framework-free):
                             models, state machines, policy, approvals, hash-chained audit,
                             planner, engine, SQLite store with restart recovery, and AI
                             tool-call proposals (`proposer.py`)
  tools/                    `ToolExecutor` protocol, dry-run executor, scripted fake for tests,
                             MCP client (`mcp_executor.py`, `mcp_convert.py`), `MCP_SERVERS_FILE`
                             loader (`servers_config.py`)
  mock_mcp/                 bundled `drsim` MCP server: nine DR tools over a simulated
                             environment, scenario file for faults (`python -m dr_agent.mock_mcp`)
backend/tests/
  conftest.py               every test gets its own database file (`DB_PATH` in `tmp_path`)
  unit/                     unit tests (`exec_support.py`, `history_support.py`: shared helpers)
  integration/              API (TestClient) and CLI (CliRunner + one subprocess) tests; execution
                             against the mock MCP server (in-memory and stdio subprocess)
  fixtures/                 parser edge-case fixtures; golden formatter snapshots (Phase 4)
frontend/                   React dashboard (Vite, React 18, TypeScript, Tailwind, Recharts)
  openapi.json              committed API schema (regenerate with `uv run poe gen-api`)
  src/api/                  generated types (`schema.d.ts`) + the single typed client
  src/hooks/                data fetching: `useAnalysis` (submit + long-poll job), `useSamples`,
                             `useExecution` (actions + polling), `useExecutionCatalog`, `useAudit`,
                             `useStoredName`, `useHistory`, `useStoredAnalysis`
  src/components/           Analyze view, input panel, report sections, charts; `history/`: stored
                             analyses list and detail; `execution/`: step cards, call view and
                             editor, header, audit panel
                             (each < 150 lines, with tests)
mock-data/
  runbooks/                 mock runbooks: estimate-service, payment-gateway, auth-service (Phase 2),
                             order-service (complete reference: every parsed field, health-check curls),
                             estimate-service-executable (every step has `Tool:` annotations)
  inventories/               mock inventories: healthy, partial-outage, major-outage (share 7 services),
                             order-service (pairs with runbooks/order-service.md)
  expected-reports/         golden reports for estimate-service: without history (Phase 4) and with
                             the history fixture in backend/tests/fixtures/history (Phase 14)
  scenarios/                mock MCP server scenarios for drills: smoke-fails-once, slow-promotion
```

## Prerequisites

| Tool | Needed for | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python and dependencies | Provides Python 3.12 automatically |
| [Ollama](https://ollama.com/) | Local LLM | Optional: only for `LLM_PROVIDER=ollama` |
| An OpenAI-compatible API key | Hosted LLM | For `LLM_PROVIDER=openai_compatible` and Docker Compose (for example Mistral or OpenAI) |
| Node.js 20+ | Frontend | `npm ci` in `frontend/` |
| Docker with Compose v2 | Container deployment | Optional; not needed for local development |

The machine used for the spike has 16 GB RAM and no discrete GPU, so a 7B model on CPU is the practical choice.

## Getting the LLM ready

Pick one provider in `.env` (copy `.env.example`). No code changes are needed to switch.

Setting up a fresh machine with a hosted API and no local model? Follow the step-by-step guide in [docs/setup-hosted-llm.md](docs/setup-hosted-llm.md).

**Hosted, OpenAI-compatible API (Mistral, OpenAI, ...).** Put your key in `.env`, never in a committed file:

```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.mistral.ai/v1      # OpenAI: https://api.openai.com/v1
LLM_MODEL=mistral-small-latest              # OpenAI: gpt-4o-mini
LLM_API_KEY=<your key>
LLM_RESPONSE_FORMAT=json_schema             # json_object for servers without JSON-schema output
```

Runbook contents are sent to that provider, so check that this is acceptable for your data.

**Local Ollama (development, no data leaves the machine).**

```
winget install --id Ollama.Ollama -e
ollama pull qwen2.5:7b-instruct
```

Then set `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://localhost:11434` and `LLM_MODEL=qwen2.5:7b-instruct`. A smaller fallback for faster, lower-quality runs is `qwen2.5:3b-instruct`.

## Development

```
uv sync                         # installs Python 3.12 and dependencies
npm ci --prefix frontend        # installs the dashboard's dependencies
uv run poe test                 # pytest (80% coverage gate) + vitest (80% thresholds)
uv run poe lint                 # ruff, ruff format --check, mypy --strict, eslint, tsc, prettier --check
uv run poe format               # ruff fix + format, prettier
uv run poe dev-api              # REST API on http://127.0.0.1:8000 (docs at /docs)
uv run poe dev-ui               # dashboard on http://localhost:5173
uv run poe build-ui             # production build into frontend/dist
uv run poe gen-api              # after an API change: refresh frontend/openapi.json + TS types
uv run poe audit                # pip-audit (locked versions) + npm audit (fails on high/critical)
```

If `uv run poe lint`, `poe test` or `poe audit` fails with `uv trampoline failed to canonicalize script path`, the venv's console-script launchers are broken. Recreate them with `uv sync --reinstall`, or run the same steps through `python -m` (for example `uv run python -m mypy --strict backend/src`, `uv run python -m pytest --cov`).

`make` is not used (not available on Windows by default); tasks are defined with [poethepoet](https://poethepoe.natn.io/) in `pyproject.toml`. A backend test fails if `frontend/openapi.json` no longer matches the API, so run `gen-api` whenever routes or models change.

## Run with Docker

From a clean machine with Docker (Compose v2) installed:

Compose runs no local model. It calls a hosted OpenAI-compatible API, so set at least `LLM_API_KEY` in a `.env` file next to `docker-compose.yml` (defaults: Mistral, `https://api.mistral.ai/v1`, `mistral-small-latest`):

```
docker compose up --build
```

Then open http://localhost:8080 for the dashboard, or http://localhost:8000/docs for the API. Without a key the `api` container exits at startup with a `CONFIG_ERROR` naming `LLM_API_KEY`. Useful variants:

```
LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o-mini docker compose up --build   # OpenAI instead
LLM_PROVIDER=none docker compose up --build                                            # rule-based only, no key
EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true docker compose up --build             # + runbook execution
MOCK_MCP_SCENARIO=/app/mock-data/scenarios/smoke-fails-once.json EXECUTION_ENABLED=true ...  # drill a failure
docker compose down                                                                    # stop (add --volumes to delete executions)
```

Compose reads `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_RESPONSE_FORMAT`, `LLM_TIMEOUT_SECONDS`, `LOG_LEVEL`, `HEALTH_CHECK_CHAOS`, `EXECUTION_ENABLED`, `EXECUTION_ALLOW_LIVE`, `EXECUTION_AI_PROPOSALS` `HISTORY_ENABLED`, `HISTORY_RETENTION_DAYS`, `KNOWLEDGE_ENABLED`, `KNOWLEDGE_IN_PROMPT` and `MOCK_MCP_SCENARIO` from your shell or the `.env` file. Stored analyses (with their runbook text) and executions are kept in the `dr-agent-data` volume. The UI image is built with an empty `VITE_API_BASE_URL`, so the browser calls `/api/...` on its own origin and nginx forwards it to the API (no CORS involved).

## Demo walkthrough

The three bundled runbooks are built to show different results. Rule-based numbers are below (`LLM_PROVIDER=none`); with a model, the score and the reasoning sections come from the LLM and vary a little between runs.

| Runbook + inventory | What to look for |
|---|---|
| `estimate-service` + `healthy` | Happy path. Score 0 (LOW), 55 min of work against a 60 min RTO (5 min buffer), all 4 dependencies UP, no rule-based gaps; the LLM still suggests improvements. CLI exit code `0` |
| `payment-gateway` + `partial-outage` | Score 100 (CRITICAL). 45 min of work against a 30 min RTO, two dependencies DOWN and one missing from the inventory (`card-network-gateway`), steps owned by "team", no validation and no rollback. CLI exit code `2` |
| `auth-service` + `major-outage` | Score 80 (HIGH). 60 min of work against a 15 min RTO, and no validation or rollback. There is no Dependencies section, so nothing can be checked against the inventory. The single-owner bus factor is a single point of failure that only the LLM reports |

1. In the dashboard, pick a runbook and inventory from the sample lists and click **Analyze runbook**.
2. Compare the risk gauge and RTO waterfall across the three samples, then filter the gap list by severity.
3. Export the report as HTML and open it offline: it is self-contained and runs no scripts.
4. Make the model unreachable (stop Ollama locally, or set a wrong `LLM_API_KEY`) and analyze again. The report still arrives, with the "AI analysis unavailable" banner and rule-based results only.
5. The CLI gives the same analysis for scripting: `uv run dr-agent analyze -r mock-data/runbooks/payment-gateway.md -i mock-data/inventories/partial-outage.json`.

**Execution drill** (the Phase 11 exit drill, scripted in `scratchpad/phase-11/browser_drill.py`). Start the mock server with a failure scenario, then the API with execution on, then the UI:

```
uv run python -m dr_agent.mock_mcp --transport http --port 8765 --allowed-host "127.0.0.1:*" --scenario mock-data/scenarios/smoke-fails-once.json
# mcp-servers.json for this: {"drsim": {"transport": "http", "url": "http://127.0.0.1:8765/mcp"}}
EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true MCP_SERVERS_FILE=<that file> uv run poe dev-api
uv run poe dev-ui
```

1. Pick `estimate-service-executable.md`, click **Analyze runbook**, then **Execute this runbook…** under the report. Type your name and click **Create dry run**. Approve every step (a second name for the two destructive steps), click **Start run** below the steps (enabled once all are approved), and confirm step 1 when asked (it has no verify tool). The run completes with simulated results; nothing reaches the server.
2. **Create live run** as the same person and try to approve step 3: refused, because whoever started a run cannot approve its destructive calls. Approve as two other people and start.
3. Step 5's smoke test fails (the injected fault) and the run pauses. Approve the rollback as two people and click **Roll back**: DNS switches back to the primary region.
4. Enter a reason and click **Abort run**, then **Load and verify** the audit log: the hash chain verifies.

With the default `mcp-servers.json` (mock server over stdio), the same works in the terminal: `EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true uv run dr-agent execute -r mock-data/runbooks/estimate-service-executable.md --operator Olivia --live`. It analyzes the runbook first, shows the risk and plan, and asks before executing.

## Dashboard

Start `uv run poe dev-api` and `uv run poe dev-ui`, then open http://localhost:5173.

The header shows whether the API is reachable and what execution allows on this server (off, dry runs only, live runs enabled). The Analyze tab walks through three stages (runbook, readiness report, execution): once a report is shown the input folds away, and "Analyze another runbook" starts over (empty editors, no report, no run). The Execution stage shows "Run in progress" once a run of the analysis exists and gets its checkmark when one completes. Every report opens with a verdict (for example "Not ready: recovery takes 45 min, the RTO is 30 min.") and key-figure tiles for recovery time, dependencies, gaps, single points of failure and track record; each tile jumps to the evidence below. Runs show a progress bar (done, needs a person, running, failed, to do), keep their controls in view above the steps, and list the steps as a timeline whose dots take the step's state colour; every colour comes with an icon or a word.

1. Pick a sample runbook and inventory (served from `API_ALLOWED_DIR`), or paste or upload your own. The inventory is optional.
2. Click **Analyze runbook**. The job runs on the server and the page long-polls it, showing the elapsed time. Expect 1-3 minutes with the 3B model and 3-5 with the 7B model on CPU, and usually well under a minute with a hosted API. With `LLM_PROVIDER=none` it finishes almost immediately.
3. Read the report: risk gauge, RTO waterfall (phases, sequential total and the RTO line), dependency health, single points of failure, gaps (filter by severity), execution plan, suggestions and summary. A banner says when AI analysis was unavailable and the results are rule-based only.
4. Export the report as JSON (built in the browser) or HTML (rendered by the server).
5. **Execute this runbook…** under the report opens an execution section below it, for the runbook that was just analyzed (there is no separate tab: execution always follows an analysis). It warns when the analysis rated the runbook HIGH or CRITICAL, and lists the runs of this analysis. There you create a dry run (every call is checked and approved, but only simulated: nothing reaches a tool) or a live run (the approved calls really run against the MCP servers). A mode's button is disabled once a run of that mode has completed for this analysis; a failed or aborted run leaves it enabled. While a request is pending (creating a run, approving, starting), the buttons are disabled and a progress note says what the server is doing, with the elapsed time; creating a run can take minutes when the AI proposes calls for steps without a `Tool:` annotation (about 10 minutes for the 6 unannotated order-service steps with a 3B model on CPU; `EXECUTION_AI_PROPOSALS=false` makes such steps manual at once). Step buttons, including **Mark done** and **Skip** on manual steps, work as soon as the run is created, before **Start run**; they need a name in "Your name", and the panel says so when it is empty. Creating a new run clears the run shown below the buttons (for example a finished live run) and shows the new one when it is ready; earlier runs stay in **Runs of this analysis** and in the History tab. While the server is calling tools in the background, a "Run in progress" note is shown and the page updates by itself. **Create live run** also needs `EXECUTION_ALLOW_LIVE=true` on the server ("Live runs are off on this server" otherwise). Below the steps, **Start run** is enabled once every step is approved (manual and skipped steps need none), and **Abort run** once the run has started. Otherwise you approve, reject, edit or skip each step's call, confirm outcomes, retry, roll back, pause, resume, close or abort, and verify the audit log. Every call is shown exactly as it would run (server, tool, arguments, risk, origin, approvals so far). Approvals are recorded under the name you type, which the page remembers in this browser only; identities are not verified, and the page says so. When execution is off on the server, the section explains how an operator turns it on. A new analysis starts a new section.
6. The page says whether the report was **saved to history**. The **History** tab lists stored analyses (newest first, filter by exact service name or risk level, load more). Opening one shows its report, a **Download runbook** link, the HTML export and **Executions of this analysis**: a read-only record of its runs. Pick a run to see its steps, calls, approvals and results, and its audit log with the hash chain verified. The History tab never starts or changes a run; to run a runbook again, analyze it on the Analyze tab, so the run follows current dependency health. When earlier analyses or live runs of the service exist, every report ends with **Historical insights** (per-step outcomes and measured times, recent runs against the RTO, dependencies that were not up), and each execution step card shows its previous live runs. Analyses older than `HISTORY_STALE_AFTER_HOURS` carry a warning that dependency health may have changed.

The API base URL comes from `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`, see `frontend/.env.example`). If the UI is served from an origin other than `http://localhost:5173`, add that origin to `CORS_ORIGINS`.

## CLI

```
uv run dr-agent analyze --runbook mock-data/runbooks/estimate-service.md --inventory mock-data/inventories/healthy.json
uv run dr-agent analyze -r mock-data/runbooks/auth-service.md -i mock-data/inventories/major-outage.json -f json -o report.json
uv run dr-agent analyze -r mock-data/runbooks/payment-gateway.md -f html -o report.html
uv run dr-agent validate --inventory mock-data/inventories/partial-outage.json [--chaos] [-f json]
uv run dr-agent parse --runbook mock-data/runbooks/payment-gateway.md
uv run dr-agent execute -r mock-data/runbooks/estimate-service-executable.md --operator Olivia [--live]
uv run dr-agent history list [--service "Estimate Service"] [--limit 20]
uv run dr-agent history show <id> [-f json|terminal|html] [--runbook] [-o FILE]
uv run dr-agent history delete <id> [--yes]
uv run dr-agent execute --analysis <id> --operator Olivia [--live]
uv run dr-agent version
```

| Option | Meaning |
|---|---|
| `--format/-f` | `json`, `terminal` (default, colored) or `html` (`validate`: `json` or `terminal`) |
| `--output/-o PATH` | Write the report to a file instead of stdout |
| `--inventory/-i PATH` | Optional for `analyze` and `execute`; without it every dependency is reported `NOT_IN_INVENTORY` |
| `--chaos` | Mock health checker randomly fails about 20% of checks |
| `--verbose/-v` | Emit logs at `LOG_LEVEL` (JSON, on stderr); otherwise warnings only |
| `--operator NAME` | `execute` only: your name, recorded as the person who started the run |
| `--live` | `execute` only: call the MCP tools (needs `EXECUTION_ALLOW_LIVE=true`); the default is a dry run |
| `--no-save` | `analyze` only: do not store this analysis in the history |
| `--analysis/-a ID` | `execute` only, instead of `--runbook`: execute a stored analysis without analyzing again |

`analyze` stores the analysis in the history and prints `Saved to history as <id>` on stderr (skip with `--no-save` or `HISTORY_ENABLED=false`). `history list` prints one line per analysis (id, time, service, risk, RTO, runs, source), so it can be piped.

`execute` needs `EXECUTION_ENABLED=true` (checked before anything else) and uses the same policy, store and MCP servers as the API. It first runs the readiness analysis and stores it (or loads it with `--analysis ID`, warning when it is older than `HISTORY_STALE_AFTER_HOURS`), prints the risk score, RTO feasibility, gap count and plan, and asks `Execute this runbook now?`; answering no exits with `0` and executes nothing. The execution then follows the report's plan. For every step that needs a person it shows the call in a panel and asks for approver names, or `reject`, `skip`, `manual`, `done`, `ok`/`failed`, `retry`, `rollback`, `close` or `abort`. A refused answer (the same approver twice, the starter approving a destructive call, a missing reason) is shown and asked again. Exit codes: `0` completed, `2` failed or aborted, `1` error.

Exit codes: `0` success, `1` error (bad input, bad config or a usage error), `2` the analysis succeeded but the risk score is critical (above 80). Reports go to stdout, while the spinner, logs and errors go to stderr, so `-f json > report.json` stays clean. Errors are printed as `{"error", "code", "details"}` JSON.

With the default 7B model on CPU an analysis takes 3-5 minutes. Set `LLM_MODEL=qwen2.5:3b-instruct` for faster, lower-quality runs, or `LLM_PROVIDER=none` for an instant rule-based-only report (no model needed).

## REST API

Start it with `uv run poe dev-api`. Interactive OpenAPI docs are at `http://127.0.0.1:8000/docs`.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/dr/analyze` | Multipart (`runbook` file + optional `inventory` file) or JSON `{runbookMarkdown, inventory?, runbookName?}`. Returns `202` with a job and a `Location` header |
| `GET /api/v1/dr/analyze?runbook=&inventory=` | Same, for files on the server, given as paths relative to `API_ALLOWED_DIR` (default `mock-data`); anything that resolves outside it is refused with `403` |
| `GET /api/v1/dr/jobs/{id}` | Poll a job: `status` is `pending`, `running`, `succeeded` (with `report`) or `failed` (with `error`) |
| `GET /api/v1/dr/jobs/{id}/report.html` | The finished report as a downloadable HTML file (autoescaped); `409 CONFLICT` while the job is unfinished |
| `GET /api/v1/dr/samples` | Sample runbooks and inventories under `API_ALLOWED_DIR` (used by the dashboard's sample picker) |
| `GET /api/v1/dr/samples/file?path=` | One sample's text, restricted to the same allow-list as `GET /api/v1/dr/analyze` |
| `GET /api/v1/health` | `{status: "ok", version, uptime}` |

Analysis history (`403 HISTORY_DISABLED` while `HISTORY_ENABLED=false`):

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/analyses?service=&riskLevel=&limit=&before=` | Stored analyses, newest first: `{items, nextBefore}`; pass `nextBefore` as `before` for the next page (`limit` 1-100, default 20) |
| `GET /api/v1/analyses/{id}` | `{summary, report, provenance, stale}`; provenance is the LLM provider, model, prompt and agent version (never credentials) |
| `GET /api/v1/analyses/{id}/runbook` | The runbook Markdown exactly as analyzed, as a `text/plain` download (never rendered) |
| `GET /api/v1/analyses/{id}/report.html` | The stored report as HTML (same rendering and CSP as the job export) |
| `GET /api/v1/analyses/{id}/executions` | Executions created from it (readable even while execution is off) |
| `GET /api/v1/analyses/{id}/executions/{executionId}` | One of them, read-only: `{execution, audit}` with the audit chain verified (also while execution is off); `404` for a run of another analysis |
| `DELETE /api/v1/analyses/{id}` | `204`; `409 CONFLICT` while executions refer to it |
| `GET /api/v1/services/{name}/history` | Knowledge-base facts for one service (steps keyed by fingerprint); `403 HISTORY_DISABLED` unless history and `KNOWLEDGE_ENABLED` are on |

Runbook execution (`403 EXECUTION_DISABLED` unless `EXECUTION_ENABLED=true`, except the settings endpoint):

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/execution/settings` | `{enabled, allowLive, approvalTimeoutMinutes, maxToolCalls, approvalsByRisk, identityVerified: false}` |
| `GET /api/v1/tools` | Allow-listed tools with their effective risk class and input schema (never server credentials) |
| `POST /api/v1/executions` | JSON `{analysisJobId, mode: dry_run\|live, startedBy}`: executes the runbook of a finished analysis job, following its execution plan; `201` with the planned execution (it records the analysis id and risk score), `404` for an unknown job, `409` while the analysis is unfinished or failed. Stored analyses can be executed after a restart |
| `GET /api/v1/executions`, `GET /api/v1/executions/{id}` | List (newest first) and detail |
| `POST /api/v1/executions/{id}/{start\|pause\|resume\|abort\|close}` | Lifecycle, body `{actor, reason?}` (a reason is required for pause, abort and close) |
| `PUT /api/v1/executions/{id}/steps/{n}/call` | Accept (omit `call`) or replace the main, verify or rollback call; clears approvals |
| `POST /api/v1/executions/{id}/steps/{n}/approve` | `{approver, callHash, comment?, kind: main\|rollback}`; `409 STALE_CALL` if the call changed |
| `POST /api/v1/executions/{id}/steps/{n}/{reject\|skip\|manual\|mark-done\|verify\|retry\|rollback}` | Human decisions, body `{actor, reason?, succeeded?}` |
| `GET /api/v1/executions/{id}/audit?verify=true` | Audit events plus hash-chain verification |

Mutating execution endpoints return the updated execution; tool calls then run in the background, and clients poll `GET /executions/{id}`. `rollback` runs the approved rollback call within the request. Errors add `403 EXECUTION_DISABLED`, `409 INVALID_TRANSITION` / `STALE_CALL`, `422 POLICY_VIOLATION` and `502 TOOL_ERROR`.

Analysis is job-based because a local model on CPU takes minutes. Add `?wait=true` to either analyze endpoint (or to the job endpoint) to wait up to `API_WAIT_TIMEOUT_SECONDS`: if the job finishes in time you get the report itself with `200`, otherwise the usual `202` job.

```
curl -F runbook=@mock-data/runbooks/payment-gateway.md -F inventory=@mock-data/inventories/partial-outage.json "http://127.0.0.1:8000/api/v1/dr/analyze"
curl "http://127.0.0.1:8000/api/v1/dr/jobs/<jobId>?wait=true"
curl "http://127.0.0.1:8000/api/v1/dr/analyze?runbook=runbooks/auth-service.md&inventory=inventories/major-outage.json"
```

Every error has the shape `{error, code, details?}`: `400 BAD_REQUEST`, `403 PATH_NOT_ALLOWED`, `404 NOT_FOUND`, `409 CONFLICT`, `413 PAYLOAD_TOO_LARGE`, `422 PARSE_ERROR` or `VALIDATION_ERROR`, `429 CAPACITY_EXCEEDED`, `500 INTERNAL_ERROR`. Each response carries `X-Request-ID` and `X-Correlation-ID` (your own values are echoed back when they are short and plain), and the same ids appear on every log line of the request and of the analysis job it starts.

Jobs are kept in memory, and every successful one is also stored in the history before it is reported as succeeded (`historySaved` on the job says whether that worked). After a restart, `GET /dr/jobs/{id}` and its HTML export answer from the history, and `POST /executions` accepts a stored analysis id.

## Analysis history

Design: [docs/design/analysis-history.md](docs/design/analysis-history.md), decisions in ADRs [0007](docs/adr/0007-persist-analyses.md) and [0008](docs/adr/0008-store-raw-runbook.md). Every successful analysis (API or CLI) is stored in the same SQLite file as executions (`DB_PATH`): the report, the parsed runbook and its raw Markdown, the inventory, and the provider, model and prompt version that produced it. Executions point to their analysis with a foreign key, so an audit trail can always be traced to the exact report and runbook it followed, and an analysis with executions cannot be deleted. The schema is upgraded in place by numbered migrations (an older execution-only database keeps its executions; a database from a newer version is refused).

Saving never fails an analysis: if the write fails, the report is still returned and marked as not saved. Analyses are kept until deleted, or for `HISTORY_RETENTION_DAYS` if set (analyses with executions are always kept). `HISTORY_ENABLED=false` stores nothing and turns the history endpoints off.

## Knowledge base

Design section 9 and ADR [0009](docs/adr/0009-knowledge-base-measured-facts.md). For the service being analyzed, the knowledge base reads up to `KNOWLEDGE_MAX_ANALYSES` stored analyses and `KNOWLEDGE_MAX_RUNS` finished **live** executions (dry runs measure nothing real, so they are only counted). An execution belongs to a service through the analysis it followed. From them, code computes:

- per step: live runs, succeeded / failed / rolled back / skipped / manual / unknown, retries, median and maximum active minutes, median elapsed minutes (approval waits included), all from audit event timestamps;
- per run: final state and end-to-end minutes against the stated RTO;
- per dependency: how often it was up, down, unreachable or not in the inventory;
- the risk score trend.

Steps are matched across runbook versions by their normalized action text and target system, so a reworded step starts a new history. The facts are used in three places:

1. **HISTORICAL gaps** (deterministic, rule-owned, counted in the rule-based score): a step failed or was rolled back in at least half of at least 2 live runs (HIGH); a step's median time is above 1.5 x its estimate (MEDIUM); completed runs took longer than the RTO (median of at least 2, HIGH); a dependency was down or unreachable in at least half of at least 3 analyses (MEDIUM).
2. **Historical insights** in the report (JSON `historicalInsights`, terminal, HTML, dashboard), left out entirely when there is no history, so reports without history are unchanged.
3. **The prompt**: a `<history>` block with an allow-list of numbers, enum values, timestamps, step numbers and names that already come from the runbook or inventory. Step summaries, tool results, reasons, rationales and earlier report text never reach the model. `KNOWLEDGE_IN_PROMPT=false` keeps even these out.

During execution, each step card (and each `dr-agent execute` step panel) shows "Previous live runs: n, failed n, rolled back n, median n min". This is information only; it never approves, skips or changes a call. `GET /api/v1/services/{name}/history` returns the raw facts. Reading history never fails an analysis: on a storage error the analysis continues without it. The mock environment's timings are simulated, so in the PoC the durations demonstrate the mechanism, not real recovery times.

## Runbook execution

The next capability after analysis is carrying out a runbook's recovery steps through [MCP](https://modelcontextprotocol.io/) tools, with a person authorizing every call. The design is in [docs/design/runbook-execution.md](docs/design/runbook-execution.md), and the decisions are in [docs/adr/](docs/adr/README.md). Phase 9 built the core (`execution/`, `tools/`). Phase 10 added the MCP client, the bundled mock MCP server and AI proposals. Phase 11 added the [REST API](#rest-api), [`dr-agent execute`](#cli), execution in the [dashboard](#dashboard) and the Compose `mock-mcp` service. Execution is never a separate step: it is started from a finished analysis (the report's execution section, `analysisJobId` in the API, or the analysis `dr-agent execute` runs first) and follows that report's execution plan. It is switched off by default: `EXECUTION_ENABLED=true` turns it on, and `EXECUTION_ALLOW_LIVE=true` additionally allows live runs. The [demo walkthrough](#demo-walkthrough) has a drill.

**Annotating a runbook.** A step can carry up to three annotations, as nested list items (or as `Tool`, `Verify Tool` and `Rollback Tool` columns in a step table). The format is `<server>/<tool> {JSON arguments}`, and the JSON object is optional:

```markdown
2. Restart the estimate-service compute nodes in the standby region. **Owner:** Bob Nguyen. Estimated time: 15 min.
   - Tool: `drsim/k8s_rollout_restart {"deployment": "estimate-service", "region": "standby"}`
   - Verify-Tool: `drsim/k8s_rollout_status {"deployment": "estimate-service", "region": "standby"}`
   - Rollback-Tool: `drsim/k8s_rollout_undo {"deployment": "estimate-service", "region": "standby"}`
```

A malformed annotation becomes a parser warning and the step falls back to an AI proposal or a manual step. Annotation code spans are never read as validation commands. `mock-data/runbooks/estimate-service-executable.md` is fully annotated for the mock server. Its verify calls state what they expect (for example `"expect_ready": true`), so a verification fails when the system is not in that state. Annotations do not change the readiness report.

**How a run works.**
- **Planning.** The planner builds one step per runbook step, in the same phases as the report. An annotated call that passes policy waits for approval. A call that fails policy goes to review with the problems listed.
- **AI proposals.** For a step without an annotation, the LLM may propose one call. It sees only the allow-listed tools, and the step text and tool descriptions are sent as escaped, delimited data. The answer must validate as a proposal and then pass the allow-list, the tool's schema and the policy constraints. Otherwise the step becomes manual with the reason recorded. A valid proposal is badged `ai_proposed` and must be accepted by a named person before anyone can approve it. With `LLM_PROVIDER=none`, or when the model is unavailable, such steps are manual.
- **Policy.** Only tools listed in the policy file can run. Arguments are validated against the tool's JSON Schema and any policy constraints. The risk class (`read`, `write`, `destructive`) comes from the policy, and a server's hints may raise it but never lower it. Tool names that look like a shell or command runner are refused.
- **Approvals.** An approval is bound to the SHA-256 of the exact call (and of its verify call). `read` and `write` calls need one approval. `destructive` calls need two different people, and neither can be the person who started the execution. Editing a call clears its approvals, and a rollback or retry needs fresh ones.
- **Running.** Steps run one call at a time, in dependency order. Right before each call the engine checks the policy, the call hash and the approvals again. A verify call follows a successful main call; a step without one waits for a person to confirm the outcome. A failure pauses the execution, and a person decides to retry, roll back (the rollback call needs its own approvals), skip with a reason, or close the execution.
- **Limits.** Each call has a timeout and each execution a maximum number of tool calls. There is a cap on active executions, and a step that waits too long for a person pauses the execution. Abort works in every non-terminal state. A call that was already sent cannot be recalled, so its step becomes `UNKNOWN` for a person to check.
- **Audit and durability.** Every change and its audit event are written to SQLite in one transaction. Audit events form a SHA-256 hash chain that can be verified. After a restart, calls that were in flight become `UNKNOWN`, running executions are paused, and nothing resumes on its own.

**Mock MCP server.** `python -m dr_agent.mock_mcp` starts the bundled `drsim` server: over stdio by default (the default `mcp-servers.json` launches it this way), or with `--transport http --port 8765` over streamable HTTP at `/mcp`. It simulates the estimate-service regional outage in memory. The nine tools are `k8s_rollout_status`, `k8s_rollout_restart`, `k8s_rollout_undo`, `db_is_in_recovery`, `db_promote_replica`, `cache_ping`, `cache_warm_from_snapshot`, `dns_switch_region` and `smoke_run`. Each declares MCP read-only and destructive hints. A scenario file (`--scenario FILE` or `MOCK_MCP_SCENARIO`) can replace the starting state and inject faults per tool:

```json
{ "faults": { "smoke_run": { "failOnCalls": [1], "message": "checkout returns 500" },
              "db_promote_replica": { "latencyMs": 2000 } } }
```

**MCP client.** `McpToolExecutor` connects to every server in `MCP_SERVERS_FILE` (stdio or streamable HTTP; `${VAR}` references are resolved from the environment and kept as secrets). It lists the tools and exposes them through the `ToolExecutor` protocol. Connecting and listing are retried with backoff. A tool call is never retried, because a recovery action that timed out may already have run.

State machines, the approval model and the security analysis are in the design doc, sections 5, 6 and 12.

## Configuration

Set through environment variables or a `.env` file (copy `.env.example`). Values are validated at startup; any invalid value stops the program with a `CONFIG_ERROR` that lists every problem.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | API port |
| `LOG_LEVEL` | `info` | Log verbosity |
| `HEALTH_CHECK_TIMEOUT_MS` | `3000` | Per-service health check timeout |
| `LLM_PROVIDER` | `ollama` | `ollama` (Ollama's native API), `openai_compatible` (any `/chat/completions` API), or `none` for rule-based analysis only |
| `LLM_MODEL` | `qwen2.5:7b-instruct` | Model name, for example `mistral-small-latest` or `gpt-4o-mini` |
| `LLM_BASE_URL` | `http://localhost:11434` | Ollama endpoint, or the API root including `/v1` for `openai_compatible` |
| `LLM_API_KEY` | (none) | Bearer token; required for `openai_compatible`. Never logged or echoed in errors |
| `LLM_RESPONSE_FORMAT` | `json_schema` | `openai_compatible` only: `json_schema`, or `json_object` for servers without JSON-schema output |
| `LLM_MAX_TOKENS` | `2048` | Output cap |
| `LLM_TIMEOUT_SECONDS` | `300` | Per-request LLM timeout |
| `HEALTH_CHECKER` | `mock` | `mock` (reads `mockStatus` from the inventory) or `live` (HTTP GET per endpoint) |
| `HEALTH_CHECK_CHAOS` | `false` | Mock checker randomly fails about 20% of checks |
| `API_HOST` | `127.0.0.1` | API bind address |
| `API_ALLOWED_DIR` | `mock-data` | Only directory `GET /api/v1/dr/analyze` may read from |
| `API_MAX_UPLOAD_BYTES` | `1048576` | Cap per uploaded file or JSON body |
| `API_WAIT_TIMEOUT_SECONDS` | `30` | Upper bound for `?wait=true` |
| `API_MAX_CONCURRENT_JOBS` | `1` | Analyses run at once (others queue) |
| `API_MAX_STORED_JOBS` | `100` | Jobs kept in memory; new jobs get `429` when this many are unfinished |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `EXECUTION_ENABLED` | `false` | Runbook execution master switch (API, `dr-agent execute`, the dashboard's execution section) |
| `EXECUTION_ALLOW_LIVE` | `false` | Second opt-in: when `false` only dry runs can be created |
| `MCP_SERVERS_FILE` | `mcp-servers.json` | MCP servers the executor may reach (`stdio` or `http`; `${VAR}` references resolved from the environment) |
| `EXECUTION_POLICY_FILE` | `execution-policy.json` | Allow-listed tools, risk classes and argument constraints |
| `EXECUTION_APPROVAL_TIMEOUT_MINUTES` | `30` | A step waiting longer for a person pauses the execution |
| `EXECUTION_TOOL_TIMEOUT_SECONDS` | `120` | Per tool call |
| `EXECUTION_MAX_TOOL_CALLS` | `50` | Upper bound per execution, verify and rollback calls included |
| `EXECUTION_MAX_ACTIVE` | `3` | Executions running or paused at the same time |
| `EXECUTION_AI_PROPOSALS` | `true` | Ask the LLM for calls for steps without a `Tool:` annotation (one model call per step when an execution is created; ignored with `LLM_PROVIDER=none`) |
| `DB_PATH` | `dr-agent.db` | SQLite file for stored analyses, executions and audit logs. `EXECUTION_DB_PATH` (the older name) is used when `DB_PATH` is not set |
| `HISTORY_ENABLED` | `true` | Store every finished analysis, including its runbook text |
| `HISTORY_RETENTION_DAYS` | `0` | Delete analyses without executions after this many days (checked at startup and after each save); `0` keeps them forever |
| `KNOWLEDGE_ENABLED` | `true` | Use stored analyses and live runs in new analyses (needs `HISTORY_ENABLED`) |
| `KNOWLEDGE_MAX_RUNS` | `10` | Most recent finished live executions considered (1-100) |
| `KNOWLEDGE_MAX_ANALYSES` | `20` | Most recent stored analyses considered (1-200) |
| `KNOWLEDGE_IN_PROMPT` | `true` | Send the allow-listed history facts to the model; `false` still reports them and uses them in rules |
| `HISTORY_STALE_AFTER_HOURS` | `24` | Stored analyses older than this get a "health may have changed" warning before they are executed |
| `MOCK_MCP_SCENARIO` | (none) | Mock MCP server only: scenario file with the starting state and injected faults |

## Swapping in real integrations

Everything external sits behind a protocol and is picked in one place, `backend/src/dr_agent/wiring.py`. `core/` and `health/` never change.

**Live health checks.** Set `HEALTH_CHECKER=live`. `LiveHealthChecker` sends an HTTP GET to every inventory service's `endpoint` in parallel (per-request timeout `HEALTH_CHECK_TIMEOUT_MS`): a 2xx response is UP, any other status is DOWN, and a timeout or connection error is UNREACHABLE. To pull health from somewhere else (Prometheus, a CMDB, a cloud API), write a class with `async def check_all(self, services) -> list[ServiceStatus]` (see `health/base.py`), inject an `httpx.AsyncClient` or SDK client into it, and return it from `build_checker()`.

> With `HEALTH_CHECKER=live` the API makes requests to whatever endpoints an uploaded inventory lists (a server-side request forgery risk). Only enable it for trusted users, or restrict outbound traffic from the API container.

**Another LLM.** An LLM provider is any class with `async def generate(self, *, system_prompt, user_prompt, schema) -> str` (see `llm/base.py`). It should return the raw JSON text, retry transport errors itself and raise `AnalysisError` when it gives up. Prompt building, JSON parsing, schema validation, the correction retry and graceful degradation are shared and stay the same. Steps:

Any server that speaks OpenAI's `/chat/completions` API (OpenAI, Mistral, Groq, OpenRouter, vLLM, llama.cpp server, LM Studio, LocalAI) already works through `LLM_PROVIDER=openai_compatible` with no code change. Connection errors, timeouts, 408, 429 and 5xx are retried with backoff; other 4xx errors (bad key, unknown model) fail at once and the report falls back to rule-based results. For an API with a different request format:

1. Add `llm/<name>.py` next to `ollama.py` and `openai_compatible.py`, with its client injected.
2. Add the name to `llm_provider` in `config.py` and a branch in `build_llm()`.
3. Test it with `httpx.MockTransport`, like `tests/unit/test_openai_compatible_provider.py`.

The providers use plain httpx, not vendor SDKs, so the core stays open source; which hosted API you point it at is a deployment choice.

**Persistence.** Jobs live in memory (`api/jobs.py`). A durable store (SQLite, Redis) can replace `JobStore` without touching the service layer. Executions already use a durable store: `ExecutionStore` (`execution/store.py`) with a SQLite implementation. A PostgreSQL store would implement the same five async methods.

**Tool execution.** The engine reaches external systems only through `ToolExecutor` (`tools/base.py`: `list_tools()` and `call_tool()`). The implementations are `McpToolExecutor` (MCP SDK), the dry-run executor and a scripted fake. A real MCP server (Kubernetes, PostgreSQL, DNS) needs no code change: add it to `MCP_SERVERS_FILE` and allow-list its tools in `EXECUTION_POLICY_FILE`, after a threat review of those tools. Only `tools/mcp_executor.py`, `tools/mcp_convert.py` and `mock_mcp/` import the SDK; a test enforces this.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Decisions and LLM spike | Done |
| 1 | Foundation: scaffolding, config, logging, errors, models | Done |
| 2 | Markdown parser and mock runbooks | Done |
| 3 | Health validator and mock inventories | Done |
| 4 | LLM analysis and report formatters | Done |
| 5 | CLI and REST API | Done |
| 6 | React dashboard | Done |
| 7 | Docker, CI, security pass, final docs | Done |
| 8 | Design for human-authorized runbook execution via MCP (design doc + ADRs) | Done (approved 2026-09-24) |
| 9 | Execution core: models, state machines, policy, approvals, audit, SQLite store, runbook tool annotations | Done |
| 10 | MCP integration: MCP client, bundled mock MCP server, AI tool-call proposals | Done |
| 11 | Execution API, CLI, UI and Docker delivery | Done |
| 12 | Design for analysis history and a DR knowledge base (design doc + ADRs 0007-0009) | Done (approved 2026-09-25) |
| 13 | Analysis history: stored reports and runbooks linked to executions, API, CLI, UI | Done |
| 14 | Knowledge base: measured facts from past runs in reports, prompts and execution | Done |

Details and exit criteria are in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). The execution feature is described in [docs/design/runbook-execution.md](docs/design/runbook-execution.md), with decisions in [docs/adr/](docs/adr/README.md).

## Security notes

- **Data leaving the machine.** With `openai_compatible` pointed at a hosted API, runbook contents and dependency health are sent to that provider. Use Ollama or a self-hosted server when that is not acceptable.
- **Prompt injection.** Runbook and inventory content is untrusted. It is embedded in the prompt as JSON inside `<runbook>` and `<validation>` delimiters, with `<`, `>` and `&` written as JSON unicode escapes, so a runbook cannot close the delimiter and write its own instructions. The system prompt tells the model to treat that content as data only. The model output is accepted only after JSON-schema validation. Deterministic facts (RTO math, dependency health, four gap types, risk level) come from code, and the LLM can't override them. The model never executes anything, so the worst case is a misleading reasoning section, not an action.
- **Input handling.** Every API input is validated with Pydantic, and uploads and JSON bodies are size-capped. Server-side files are read only inside `API_ALLOWED_DIR` (resolved-path containment plus an extension allow-list). Errors never echo server paths or raw input, internal errors become a generic `500`, and client request IDs are accepted only when short and plain.
- **Output.** The HTML report is autoescaped (Jinja2) and served with a strict CSP (`default-src 'none'`, no scripts). The React UI never renders raw HTML. API responses carry `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy`, and the nginx-served dashboard adds a same-origin CSP.
- **Secrets and logs.** Configuration comes from the environment, and `.env` is gitignored and excluded from Docker build contexts. `LLM_API_KEY` is held as a `SecretStr` and scrubbed from provider error details. Logs redact secret-looking keys and strip `user:password@` from any URL, including in tracebacks. Runbook text is never logged.
- **Containers.** Containers run as non-root, with read-only root filesystems, all capabilities dropped and `no-new-privileges`. Ports are bound to `127.0.0.1`. The API container needs outbound HTTPS to the configured LLM API.
- **Dependencies.** `uv run poe audit` (pip-audit on the locked versions plus npm audit) runs in CI. Every dependency is open source.
- **Runbook execution (core only, off by default).** Annotations in a runbook and AI proposals are both untrusted input. They pass the same allow-list, JSON Schema, constraint and approval checks, and an AI proposal additionally needs a named person to accept it. Step text and tool descriptions reach the model only as escaped, delimited data, and the model is offered allow-listed tools only. Nothing runs without approvals bound to the exact call hash, and the checks are enforced in `execution/`, not in any UI. There is no shell tool. Tool results are validated, truncated to 16 KB, stored as data and never fed back to an LLM. MCP servers come only from `MCP_SERVERS_FILE`; their credentials (`${VAR}` references) are never logged or included in errors. The bundled mock MCP server is for drills only, and its HTTP transport has no authentication, so keep it on an internal network. Approver names are not authenticated (the two-person rule guards against mistakes, not a malicious user), and the audit chain has no external anchor yet. See the design doc, section 12.
- **Execution API and UI.** All execution checks run on the server, so calling the API directly bypasses nothing: the UI has no authority. Tool results, AI rationales and audit payloads are rendered as text, never as HTML. The mock server's HTTP transport only accepts its own Host name (DNS-rebinding protection) and runs on an internal network with no published port.
- **History in prompts.** Past runs reach the model only as the allow-listed facts of `knowledge/prompt_facts.py` (numbers, enum values, timestamps, step numbers, runbook and inventory names), escaped inside `<history>` like the other blocks. Step summaries, tool results, reasons, rationales and earlier report text are never sent, so a runbook or tool that once carried an injection attempt cannot reach later analyses through the history. A test enforces the allow-list.
- **Stored runbooks.** The history keeps each runbook's full text and inventory (ADR 0008), which may include hostnames, IP addresses and internal procedures. The database file is gitignored, excluded from Docker build contexts and kept on the `dr-agent-data` volume, but it is not encrypted: use disk encryption, set `HISTORY_RETENTION_DAYS`, or turn the history off with `HISTORY_ENABLED=false`. Anyone who can reach the API can read every stored runbook. Stored Markdown is only served as a `text/plain` download and shown as text, and runbook text is still never logged.
- **Known limits (PoC).** There is no authentication or rate limiting, only a job concurrency cap. Anyone who can reach the API can read stored analyses and runbooks, start executions and approve calls under any name, so keep execution off, or the API on localhost or behind an authenticating proxy. `HEALTH_CHECKER=live` is an SSRF surface (see above). Put the API behind an authenticating proxy before exposing it beyond localhost.

## License

To be decided. All dependencies are open source.
