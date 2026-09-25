# Phase 6 Summary: React dashboard

Date: 2026-09-23. Status: **Done**.

## Phase 0-5 validation (done first)
Re-ran the full gate before starting: `uv run poe lint` (ruff check, ruff format
--check, mypy --strict on 63 files) and `uv run poe test`. Both green: 359 tests,
98.75% coverage, the same numbers as `scratchpad/phase-5/SUMMARY.md`. Also checked the
non-negotiables across `backend/src`: no file over 200 lines, no `Any`, no bare
`except`, no FastAPI/Typer/Rich/Starlette imports in `core/` or `health/`. CLI smoke
test (`LLM_PROVIDER=none dr-agent analyze` on estimate-service + healthy) printed
valid JSON and exited 0. Ollama has `qwen2.5:3b-instruct` and `qwen2.5:7b-instruct`
pulled. Node 26.1 / npm 11.16 are installed.

Carried over, still open: the Phase 5 **risk-score reliability decision**.
auth-service + major-outage exits 0, not 2 (the rule fallback scores it 80, which is
not > 80). Phase 6 doesn't depend on it. The options are listed in the Phase 5
summary, and none of them has been applied without your decision.

## What was built
| Area | Files |
|---|---|
| Backend: HTML export | `GET /api/v1/dr/jobs/{id}/report.html` in `api/routes.py`: the finished job's report through the existing autoescaped Jinja2 `format_html`, served as `attachment`. Returns `409 CONFLICT` while the job is unfinished (new `ConflictError` in `utils/errors.py`, mapped in `api/errors.py`) |
| Backend: sample picker | `api/routes_samples.py`: `GET /api/v1/dr/samples` (lists `runbooks/*.md` and `inventories/*.json` under `API_ALLOWED_DIR`) and `GET /api/v1/dr/samples/file?path=` (goes through the same `resolve_allowed_path` allow-list as `GET /analyze`). New `SampleList`/`SampleFile` in `api/schemas.py` |
| Backend: client generation | `api/export_openapi.py` writes the deterministic OpenAPI JSON. `uv run poe gen-api` = dump to `frontend/openapi.json`, then `openapi-typescript`, which writes `frontend/src/api/schema.d.ts` |
| Frontend scaffolding | `frontend/`: Vite 8, React 18.3, TypeScript 5.9 strict (`noUncheckedIndexedAccess`), Tailwind 4 (`@tailwindcss/vite`), Recharts 3, `openapi-fetch`. Config: `vite.config.ts` (vitest + v8 coverage thresholds of 80%), `tsconfig.json`, `eslint.config.js` (typescript-eslint strict, react-hooks, `no-explicit-any`, `max-lines` 200), `.prettierrc.json`, `.env.example` (`VITE_API_BASE_URL`) |
| API layer | `src/api/client.ts` (the single typed client: `submitAnalysis`, `pollJob` long-poll, `listSamples`, `getSample`, `reportHtmlUrl`; errors normalised to `ApiError{message, code, status}`, with `NETWORK_ERROR` when the API is unreachable). `src/api/types.ts` only aliases generated types |
| Hooks | `useAnalysis` (state machine idle → submitting → running(jobId) → done/error; a run ID stops results from stale or abandoned runs being applied; loops with `?wait=true`), `useSamples` |
| Components | `InputPanel` (paste or upload runbook + inventory, sample picker, JSON syntax check), `TextSource`, `SamplePicker`, `LoadingPanel`/`ErrorPanel`, `ReportView` (AI-unavailable banner, executive summary, JSON/HTML export), `RiskGauge` (half-circle Recharts radial bar + text score and level badge), `RtoTimeline` (waterfall of execution phases + sequential total bar + dashed RTO reference line, text verdict/buffer/bottlenecks), `DependencyTable`, `SpofList`, `GapList` (severity toggle filter with counts), `ExecutionPlan`/`Suggestions`, `Badge`, `Section` |
| Lib | `lib/labels.ts` (icon + text + color for risk/severity/status), `lib/waterfall.ts`, `lib/download.ts` |
| Tooling | `pyproject.toml` poe tasks: `test` = pytest + vitest; `lint` = ruff + mypy + (eslint, `tsc`, prettier --check); `format` also runs prettier; new `dev-ui`, `build-ui`, `gen-api`. `.gitignore`: `frontend/coverage/`, `*.tsbuildinfo`. CI (`.github/workflows/ci.yml`) now sets up Node 22, runs `npm ci`, and builds the UI |
| Tests | Backend: `test_api_samples_export.py` (10), `test_openapi_export.py` (4), plus a 409 case in `test_api_paths_errors.py` and the route list update in `test_api_platform.py`. 374 tests in total (15 new), 98.79% coverage. Frontend: 7 files, 42 tests, 99.5% lines / 89.6% branches |

## Design decisions
| # | Decision | Reason |
|---|---|---|
| P6-1 | Typed client = `openapi-typescript` (types) + `openapi-fetch` (runtime), generated from a **committed** `frontend/openapi.json`. `test_openapi_export.py::test_committed_schema_is_current` fails when it is stale | Rule "API types come from the backend OpenAPI schema". A committed schema means the frontend builds without a running backend, and the drift test keeps the two in sync. Both libraries are MIT |
| P6-2 | The UI always uses the JSON body. Uploaded files are read in the browser (`File.text()`) into the editors | One request path. The user can see and edit what gets analyzed. The inventory's JSON syntax is checked on the client, and the server still validates everything with Pydantic. Multipart remains for curl/CLI users |
| P6-3 | Jobs never use `?wait=true` on submit. They are then long-polled with `GET /jobs/{id}?wait=true`, with a 1 s pause between polls that return unfinished | A 7B model on CPU takes minutes. Long-polling gives few requests and immediate completion without hot loops. The poll interval can be injected, so tests run with 0 |
| P6-4 | Sample picker loads file **contents** through a new allow-listed endpoint instead of calling `GET /analyze?runbook=path` | Lets the user see and tweak the sample before analyzing, and keeps one submit path (P6-2). It reuses `resolve_allowed_path` (traversal, extension allow-list, 403/404 tested) |
| P6-5 | HTML export is server-rendered (`/jobs/{id}/report.html`) and JSON export is client-side (Blob) | The Jinja2 template is already the autoescaped, snapshot-tested HTML report. Duplicating it in React would drift. JSON needs no server round trip |
| P6-6 | RTO chart shows phase bars **and** a "Total" bar. A caption explains that the RTO check uses the sequential sum | Found in the browser: without LLM step dependencies, every step falls into one parallel phase (10 min) while the RTO math uses the 45 min sum. A phases-only chart looked feasible next to a "Not feasible" verdict |
| P6-7 | Generated types keep response defaults as required (openapi-typescript default), so request objects pass `inventory: null, runbookName: null` explicitly | The server always serializes defaults, so required response fields are accurate, and the UI doesn't need `?? default` for them. List fields that FastAPI marks optional are defaulted with `?? []` |
| P6-8 | Accessibility: every severity, status and risk badge has an icon and text, not color alone. Sections are `region`s labelled by their heading. Charts are `role="img"` with an `aria-label`, and their numbers are also shown as text. The loading panel is a `status` live region. Errors use `role="alert"`. Focus moves to the report when it arrives | Rule "color is never the only severity signal". The tests query by role and label only |
| P6-9 | TypeScript pinned to `~5.9` | TS 6.x conflicts with `openapi-typescript`'s peer range (`^5`), and 6.1+ with `typescript-eslint` |
| P6-10 | `chunkSizeWarningLimit: 700` instead of code-splitting | Recharts makes the bundle ~553 kB (165 kB gzip). That's fine for an internal single-page dashboard. Revisit in Phase 7 if needed |
| P6-11 | Playwright smoke test not added to the repo (the plan marks it optional). The browser demo was driven through the Playwright MCP instead (below) | Avoids a ~150 MB browser download in CI for the PoC. RTL covers the flow (`App.test.tsx`: sample → job → report, the AI-unavailable state, and errors) |

## Browser verification (exit criterion)
Ran `uv run poe dev-api` + `uv run poe dev-ui` and drove Chromium through the Playwright MCP.
Screenshots are in `results/`:
| Run | Result |
|---|---|
| `LLM_PROVIDER=none`, payment-gateway + partial-outage | All sections render. Score 100 CRITICAL, AI-unavailable banner with `aiNote`, 3/4 deps not up, 6 rule gaps, severity filter works. (`payment-gateway-partial-outage-rules.png`, taken **before** the P6-6 chart fix) |
| `LLM_PROVIDER=none`, auth-service + major-outage | Score 80 HIGH, "Not feasible: 60 min vs 15 min", Total bar clearly past the RTO line, no Dependencies section → empty state. (`auth-service-major-outage-rules.png`) |
| `qwen2.5:3b-instruct`, payment-gateway + partial-outage | Loading panel with elapsed time and job id (`loading-state.png`). Finished in 127.1 s: score 75 HIGH, 2 execution phases from LLM step dependencies, 1 SPOF, 11 gaps (6 rule + 5 LLM), 5 prioritized suggestions, LLM summary. (`payment-gateway-partial-outage-llm-3b.png`) |
| HTML export | `curl .../jobs/{id}/report.html` → 200, `text/html`, `attachment`. A `<script>` in the runbook came back escaped (`export-sample.html`) |
Only console error seen: a missing `favicon.ico` (fixed with an inline SVG icon).

## Exit criteria
| Criterion | Result | Evidence |
|---|---|---|
| Vite + React + TS + Tailwind; typed client generated from OpenAPI | Done | `frontend/`, `poe gen-api`, drift test |
| Upload/paste runbook and inventory, sample picker | Done | `InputPanel.test.tsx` (7 tests), browser runs |
| Risk gauge, RTO timeline/waterfall with buffer, dependency table, SPOF + gap lists with severity filter, execution plan, suggestions, executive summary | Done | `ReportView.test.tsx`, `sections.test.tsx`, screenshots |
| Export JSON/HTML | Done | `ReportView.test.tsx` export test, `test_api_samples_export.py`, curl check |
| Loading and AI-unavailable states | Done | `App.test.tsx`, `loading-state.png`, rule-only screenshots |
| vitest + RTL tests | Done | 42 tests, 99.5% lines, 80% thresholds enforced |
| Playwright smoke test (optional) | Skipped | P6-11; manual MCP-driven run instead |
| Full demo path works in browser against mock data | Done | Browser verification above |

## Caveats and follow-ups
- Risk-score decision from Phase 5 is still open (see above).
- The UI runs one analysis at a time and keeps nothing: reloading the page loses the report (plan question 3: no persistence). The job survives on the server until evicted, but the UI does not resume it.
- The API's `CORS_ORIGINS` default only allows `http://localhost:5173`. Opening the UI as `http://127.0.0.1:5173` requires adding that origin.
- "Kill Ollama and confirm graceful degradation" (plan verification) was exercised with `LLM_PROVIDER=none`. The transport-failure degradation path is covered by the Phase 4 tests; the Docker-kill variant belongs to Phase 7.
- Vitest on this Windows machine takes about 95 s, mostly jsdom environment setup. The tests themselves take under 1 s.

## Commands verified
```
uv run poe gen-api     # regenerate frontend/openapi.json + src/api/schema.d.ts
uv run poe lint        # ruff, ruff format --check, mypy --strict, eslint, tsc, prettier --check
uv run poe test        # pytest 374 passed 98.79% + vitest 42 passed
uv run poe build-ui    # vite production build
uv run poe dev-api     # API on :8000
uv run poe dev-ui      # UI on http://localhost:5173
```
