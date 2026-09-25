# DR Readiness Agent

AI-powered Disaster Recovery readiness tool. Parses Markdown DR runbooks, validates dependencies against a (mock) health inventory, and produces a readiness report (risk score, RTO feasibility, SPOFs, gaps, execution plan) using a local open-source LLM.

Source of truth:
- Requirements: `AI-Powered Disaster.md` (original brief, written for Node/Claude; stack has been translated)
- Approved plan and phases: `docs/IMPLEMENTATION_PLAN.md`
- Designs: `docs/design/runbook-execution.md` (Phases 8-11), `docs/design/analysis-history.md` (Phases 12-14); decisions in `docs/adr/`

## Stack (open source only)
- Backend: Python 3.12, FastAPI, Pydantic v2, Typer + Rich, markdown-it-py, httpx, structlog, Jinja2
- LLM: `LLMProvider` protocol. `LLM_PROVIDER=ollama` (local) or `openai_compatible` (any `/chat/completions` API, e.g. OpenAI or Mistral, with `LLM_API_KEY`), chosen by config only. Plain httpx, no vendor SDKs in core.
- Frontend: React 18 + TypeScript + Vite + Tailwind + Recharts
- Quality: uv, ruff, mypy --strict, pytest (+asyncio, cov), vitest + React Testing Library
- Execution: official MCP Python SDK (`mcp`) only in `tools/mcp_*.py` and `mock_mcp/`; `jsonschema`; SQLite (stdlib)
- History: stored analyses (with runbook text) and executions share one SQLite file (`DB_PATH`, numbered migrations in `storage/`); `knowledge/` turns them into measured facts for new analyses (`KNOWLEDGE_*`)
- Delivery: Docker Compose (api, ui, mock-mcp on an internal network; LLM is a hosted OpenAI-compatible API, no local model), GitHub Actions (`docker/` holds Dockerfiles + nginx.conf)

## Layout
```
backend/src/dr_agent/{config.py,service.py,loaders.py,wiring.py,cli*.py,models,core,health,llm,formatters,api,utils,execution,tools,mock_mcp,storage,history,knowledge}
backend/tests/{unit,integration,fixtures}
frontend/
mock-data/{runbooks,inventories,expected-reports}
docs/
```

## Commands (`make` is not available on this machine, tasks use poethepoet)
All tasks are available (Phase 6 added the frontend to `test`, `lint` and `format`).
```
uv sync                 # install backend (Python 3.12 pinned); npm ci in frontend/
uv run poe test         # pytest --cov + vitest --coverage
uv run poe lint         # ruff check + ruff format --check + mypy --strict + eslint/tsc/prettier --check
uv run poe format       # ruff + prettier
uv run poe dev-api      # uvicorn on :8000 (python -m dr_agent.api)
uv run poe dev-ui       # vite on :5173
uv run poe build-ui     # vite production build
uv run poe gen-api      # after API changes: refresh frontend/openapi.json + src/api/schema.d.ts (drift is tested)
uv run poe audit        # pip-audit (locked deps) + npm audit --audit-level=high
docker compose up --build   # ui :8080, api :8000; needs LLM_API_KEY in .env (default Mistral); LLM_PROVIDER=none for rules only
                            # EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true for runbook execution against mock-mcp
uv run dr-agent analyze --runbook mock-data/runbooks/estimate-service.md --inventory mock-data/inventories/healthy.json
LLM_PROVIDER=none uv run dr-agent analyze ...   # rule-based only, no model (fast, deterministic)
uv run python -m dr_agent.mock_mcp [--transport http --port 8765] [--scenario FILE]   # bundled mock MCP server
EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true uv run dr-agent execute -r mock-data/runbooks/estimate-service-executable.md --operator NAME [--live]   # analyzes first, then asks
uv run dr-agent history list | show ID [--runbook] | delete ID      # stored analyses; execute --analysis ID runs one again
```
If a `poe` task fails with `uv trampoline failed to canonicalize script path` (broken venv launchers on this machine), run `uv sync --reinstall` or the same step via `uv run python -m mypy|pytest|pip_audit|poethepoet`.

## Non-negotiables
- Work phase by phase per `docs/IMPLEMENTATION_PLAN.md`. Do not start a phase before the previous exit criteria pass.
- Tests are written with the code, not after. Coverage must stay above 80%.
- No `Any`, no bare `except`, no untyped functions. Errors derive from `AppError`.
- `core/`, `health/`, `execution/` and `tools/` must not import FastAPI, Typer or other framework code. Providers, tool executors and stores are injected.
- Files stay under 200 lines. Split by responsibility.
- All external input (files, API bodies, LLM output) is validated with Pydantic at the boundary.
- Every finished analysis is stored (ADR 0007/0008) unless `HISTORY_ENABLED=false` or `--no-save`; saving must never fail an analysis. Tests get their own database through `backend/tests/conftest.py`.
- Execution always follows an analysis: executions are created from a finished analysis job (API `analysisJobId`, CLI analyzes first, UI section under the report) and follow its execution plan. Do not add a standalone execution entry point.
- Runbook text is untrusted. It is delimited in prompts and LLM output is only accepted if it passes schema validation.
- History reaches a prompt only through the allow-list in `knowledge/prompt_facts.py` (code-measured numbers and names, ADR 0009). Never add summaries, tool results, reasons, rationales or report text to it.
- All external systems are mocked in the PoC. Real integrations must only need a different injected implementation.
- Never commit secrets. `.env` is never read or written by the agent; edit `.env.example` only.
- Do not add dependencies that are not open source.

## Working style
- Ask before changing the scope or the stack. State assumptions when the brief is ambiguous.
- Prefer small, reviewable changes. Run `uv run poe lint` and `uv run poe test` before declaring a phase done.
- Phase status lives in `docs/IMPLEMENTATION_PLAN.md` and the README roadmap. Each finished phase gets a summary in `scratchpad/phase-N/SUMMARY.md`.
- Hosted LLM: `openai_compatible` with `LLM_BASE_URL` (API root incl. `/v1`), `LLM_MODEL`, `LLM_API_KEY`; the key lives only in the user's `.env`.
- Local LLM: Ollama with `qwen2.5:7b-instruct` (default) or `qwen2.5:3b-instruct` (fast dev). CPU only, about 5 tokens/s for 7B, so analysis is job-based.
- Detailed conventions live in `.claude/rules/`. Reusable workflows are in `.claude/commands/` and `.claude/skills/`.

## Claude Code setup in this repo
- `.claude/settings.json`: permissions and pre/post tool hooks
- `.claude/hooks/`: `guard_bash.py`, `guard_files.py`, `post_edit.py`
- `.claude/rules/`: path-scoped coding rules
- `.claude/commands/`: `/phase`, `/test`, `/demo`, `/review-phase`, `/new-runbook`
- `.claude/skills/`: `dr-runbook-parser`, `llm-structured-output`, `phase-workflow`
- `.mcp.json`: context7 (library docs), playwright (UI verification)
