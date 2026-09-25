# Phase 7 Summary: Hardening and delivery

Date: 2026-09-23. Status: **Done, with the Docker exit criterion only partly verified**. Docker isn't installed on this machine. See "Exit criteria" below.

## Phase 0-6 validation (done first)
I read `docs/IMPLEMENTATION_PLAN.md`, `README.md` and `.claude/rules/`, then re-ran the full gate before changing anything:
- `uv run poe lint`: ruff check, ruff format --check (117 files), mypy --strict (65 files) and eslint/tsc/prettier all clean.
- `uv run poe test`: 377 backend tests, 98.79% coverage; 42 vitest tests, 99.48% lines. These match the Phase 6 numbers (374, plus 3 tests added after that summary).
- No `.py`/`.ts`/`.tsx` file is over 200 lines (the generated `schema.d.ts` is excluded).
- CLI smoke test with `LLM_PROVIDER=none`: estimate-service + healthy exits 0, payment-gateway + partial-outage exits 2 (score 100), and auth-service + major-outage exits 0 (score 80, HIGH).
- The one pytest warning is a starlette/anyio deprecation inside `.venv`, not our code.

Every summary from phase 0 to 6 is present, and every checkbox in the plan is ticked. **Still open from Phase 5:** the risk-score decision (auth-service + major-outage scores exactly 80, so it exits 0, not 2). Phase 7 does not depend on it and I did not change it.

## What was built
| Area | Files |
|---|---|
| API image | `docker/api.Dockerfile`. The build stage takes `uv` pinned at 0.12.10 and runs `uv sync --frozen --no-dev --no-install-project` (a cached dependency layer), then `--no-editable` into `/opt/venv`. The runtime is `python:3.12-slim-bookworm` with only that venv and `mock-data`: UID 10001, `API_HOST=0.0.0.0`, `API_ALLOWED_DIR=/app/mock-data`, and a `HEALTHCHECK` on `/api/v1/health` (stdlib urllib, no curl in the image) |
| UI image | `docker/ui.Dockerfile`. `node:22-alpine` runs `npm ci` and `npm run build` (`tsc -b` + vite) with `VITE_API_BASE_URL=""`. The runtime is `nginxinc/nginx-unprivileged:1.30-alpine` on port 8080, with a `/healthz` healthcheck |
| nginx | `docker/nginx.conf`. It does the SPA fallback and proxies `/api/` to `http://api:8000` (120 s read timeout for long-polls, 3 MB body cap). `location /` sends a CSP (`default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'` for Recharts, `img-src 'self' data:`, `connect-src 'self'`, `frame-ancestors 'none'`), `nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`. `server_tokens off` |
| Compose | `docker-compose.yml` defines `ollama` (models volume, `ollama list` healthcheck, no host port), `ollama-pull` (one-shot `ollama pull ${LLM_MODEL}`), `api` and `ui`. The start order is enforced: ollama healthy, then pull done, then api healthy, then ui. A shared `x-hardening` anchor makes the filesystem read-only with a `/tmp` tmpfs, sets `cap_drop: [ALL]` and `no-new-privileges`. Ports are bound to `127.0.0.1`. The environment passes through `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS` (default 600 in containers), `LOG_LEVEL` and `HEALTH_CHECK_CHAOS` |
| Build context | `.dockerignore` excludes `.env*` (except the examples), `.venv`, caches, tests, `scratchpad`, `docs`, `.claude`, `node_modules`, `dist` and coverage |
| CI | `.github/workflows/ci.yml` gains `permissions: contents: read`. `quality` is unchanged. The new `audit` job runs `uv run poe audit`. The new `docker` job runs `compose config`, builds `api ui`, then `LLM_PROVIDER=none up --no-deps --wait api ui` and curls through the UI proxy: `/healthz`, `/api/v1/health`, and `GET analyze?wait=true` (asserting `riskLevel` and `executionPlan`), and checks the CSP header. It always dumps logs and runs `down --volumes` |
| Audit task | `pyproject.toml` gets `poe audit` = `_pip-audit` (`uv export --frozen --all-groups` into `.venv/audit-requirements.txt`, then `pip-audit --require-hashes --disable-pip`, so it checks the exact locked versions) + `_npm-audit` (`--audit-level=high`). New dev dependency: `pip-audit` (Apache-2.0, named in the plan) |
| Prompt hardening | `llm/prompts/analysis.py`: the new `prompt_json()` writes `<`, `>` and `&` as JSON unicode escapes (a `str.translate` table), so the result is still valid JSON that decodes to the same text |
| Log/secret hardening | `utils/logging.py`: the new `scrub_url_credentials()` turns `scheme://user:pass@host` into `scheme://***@host`. `redact_secrets` applies it to every string value and now runs **after** `format_exc_info`, so tracebacks are scrubbed too. `llm/ollama.py` scrubs the `AnalysisError` reason |
| Response headers | `api/middleware.py`: `security_headers_middleware` (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`) and `REPORT_CSP`. `api/routes.py` sets that CSP on `report.html`. It's registered in `api/app.py` |
| Frontend | `src/api/client.ts` treats an empty base URL as same-origin, and the network error no longer reads "at ." |
| Tests | Backend: `test_prompts.py` (4: escaping, delimiter forging, round-trip, system prompt stance), plus 6 in `test_logging_timing.py` (4 URL cases, string values, traceback scrubbing), 1 in `test_ollama_provider.py` (no credentials in the reason), 1 in `test_api_platform.py` (headers on success and error responses) and CSP asserts in `test_api_samples_export.py`. That makes **389 tests (12 new), 98.80%**. Frontend: 1 new client test, **43 tests** |
| Docs | README: status, stack, deployment diagram, layout, prerequisites, `poe audit`, "Run with Docker", "Demo walkthrough", "Swapping in real integrations", rewritten "Security notes", and the roadmap. `docs/IMPLEMENTATION_PLAN.md` Phase 7 is ticked with its results. `CLAUDE.md` has the new commands |

## Design decisions
| # | Decision | Reason |
|---|---|---|
| P7-1 | The UI container serves the app **same-origin** and nginx proxies `/api/` | No CORS setup, a tight CSP (`connect-src 'self'`), and one published port is enough for the dashboard. The API port stays published (localhost only) for curl and `/docs` |
| P7-2 | Model download is a separate one-shot `ollama-pull` service that `api` waits for (`service_completed_successfully`) | The API never starts against a missing model, and the named volume makes later starts instant. With rules only, `--no-deps api ui` skips Ollama entirely |
| P7-3 | The compose default model stays `qwen2.5:7b-instruct`, and `LLM_MODEL` overrides it | Consistent with `config.py` and Phase 0 decision D1. The README gives the 3B and rule-only alternatives for faster demos |
| P7-4 | The CI Docker smoke test runs with `LLM_PROVIDER=none` | Pulling 4.7 GB and running a 7B model on a CI runner is slow and flaky. Real-model behaviour was already verified in Phases 4-6 |
| P7-5 | The CSP is global in nginx but **per-route** in the API (report export only) | FastAPI's `/docs` loads Swagger UI from a CDN with inline script, so a global API CSP would break it. The report is self-contained, so it gets `default-src 'none'` |
| P7-6 | Prompt delimiters are protected by escaping, not by stripping or rejecting | The runbook text stays visible to the model (it may be worth flagging as a gap) but can't end the data block. JSON unicode escapes are standard, and models read them fine |
| P7-7 | `pip-audit` audits the exported lock with hashes, instead of the environment | The uv venv has no pip, and auditing the lock covers exactly what CI and the image install. `/dev/stdin` does not work on Windows, so the export goes to a temp file in `.venv/` (gitignored) |
| P7-8 | Pinned base images, checked against the registries on 2026-09-23 | `nginx-unprivileged:1.27-alpine` was last updated 2025-06 (end of life), so it's `1.30-alpine` (current stable). `uv:0.12.10` matches the local uv. `ollama/ollama:latest` is left unpinned on purpose: model-server updates are wanted, and there's no API contract risk beyond `/api/chat` |
| P7-9 | SSRF from `HEALTH_CHECKER=live` + uploaded inventories: **documented, not changed** | Live mode is off by default and the PoC mocks all external systems. A host allow-list setting would change scope, so it's listed as a follow-up for you to decide |

## Security review (the plan's "security pass")
| Area | Finding | Action |
|---|---|---|
| Prompt injection | A runbook step containing `</runbook>` appeared verbatim in the prompt (`json.dumps` does not escape `<`/`>`), so it could fake the end of the data block | **Fixed** (P7-6) and tested |
| Secrets in errors/logs | httpx error strings quote the full URL. A `LLM_BASE_URL` with credentials would leak into the `AnalysisError` reason and into log tracebacks | **Fixed** by scrubbing URL credentials everywhere in logs and in the reason |
| Browser hardening | API responses had no `nosniff` or frame protection. The downloaded HTML report had no CSP | **Fixed** with a middleware and a strict report CSP |
| Input validation, size caps, path allow-list, error shape, request-id sanitising | Reviewed, already correct (Phase 5 tests cover them) | None |
| XSS | Jinja2 autoescape is on, and the UI has no `dangerouslySetInnerHTML`/`innerHTML` | None |
| Logging of runbook content | Only structured events (`runbook_parsed`, `analysis_completed`, `request_completed`, ...). A live run's log had no runbook text | None |
| Dependencies | `pip-audit`: no known vulnerabilities. `npm audit`: 0 vulnerabilities | Now enforced in CI |
| SSRF (live health checks) | Uploaded inventory endpoints are fetched when `HEALTH_CHECKER=live` | Documented in the README (P7-9) |
| AuthN / rate limiting | None. There's only a concurrency and backpressure cap | Documented as a PoC limit. Put an authenticating proxy in front before exposing the API |

## Verification without Docker
Docker isn't installed on this machine (Phase 0), so I checked every piece the images depend on separately:
1. **Wheel contents**: `uv build --wheel` includes `dr_agent/templates/report.html.jinja`, so the non-editable install in the image can render HTML reports.
2. **Image tags**: the ghcr.io and Docker Hub registry APIs return 200 for all 5 pinned tags.
3. **Compose structure**: parsed with PyYAML. Every `depends_on` target exists, both Dockerfiles exist, and the anchors merge. (`docker compose config` itself runs in CI.)
4. **API with container settings**: `API_HOST=0.0.0.0`, an absolute `API_ALLOWED_DIR`, and a working directory containing only `mock-data`, run with `python -m dr_agent.api`. Health returned 200 with the new headers.
5. **Same-origin UI behind the nginx rules**: I built the UI with `VITE_API_BASE_URL=` and confirmed `createApi("")` is in the bundle. A stand-in server (`nginx_standin.py`, in the session scratchpad) served it with the **headers parsed from `docker/nginx.conf`**, the SPA fallback and `/api/` proxying. In Chromium (Playwright MCP) with payment-gateway + partial-outage, all 5 API calls stayed same-origin (samples, sample files, POST analyze 202, poll 200). The report rendered with **0 console errors or warnings**, so no CSP violations. See `results/ui-same-origin-csp.png`. Through the proxy, the HTML export carried the strict CSP and `attachment`, `../pyproject.toml` returned 403, `/some/route` fell back to 200, and `GET analyze?wait=true` returned score 80 HIGH for auth-service + major-outage.

A second, clean venv (the exact `uv sync --no-editable` of the image) was not built: the tool call was declined, so I used the project venv for step 4.

## Exit criteria
| Criterion | Status | Evidence |
|---|---|---|
| Multi-stage Dockerfiles, compose (api, ui, ollama with model pull), healthchecks | Done | `docker/`, `docker-compose.yml`, verification steps 1-5 |
| GitHub Actions: ruff, mypy, pytest `--cov-fail-under=80`, UI lint/test/build | Done | `quality` job (as before) plus `audit` and `docker`. It has not run remotely yet: the directory is not a git repo |
| Security pass: sanitisation, prompt-injection note, no secrets in logs, dependency audit | Done | Security review above: 3 fixes with tests, and both audits clean |
| README: setup, usage, ASCII architecture, demo walkthrough, swap-to-real-integration guide | Done | `README.md`. The walkthrough numbers were checked against actual rule-based output |
| `docker compose up` gives a working demo from a clean machine | **Partial** | It couldn't be run here (no Docker). Every part the images depend on was verified separately (above). The CI `docker` job runs the rule-based compose smoke test on the first push. The full LLM path in compose (the model pull, then analysis) has not been run anywhere yet |

Gate after Phase 7: `uv run poe lint` is clean. `uv run poe test` gives 389 backend tests (98.80%) and 43 UI tests (99.48% lines). `uv run poe audit` finds no vulnerabilities.

## Caveats and follow-ups (your decision)
1. **Run `docker compose up --build` once on a machine with Docker**, or push to GitHub to run the `docker` CI job. That closes the partial exit criterion. On Windows, give Docker Desktop at least 8 GB of RAM for the 7B model.
2. **The Phase 5 risk-score decision** is still open (the exit-2 threshold is `> 80`, and auth-service + major-outage scores exactly 80).
3. **SSRF allow-list** for `HEALTH_CHECKER=live` (e.g. `HEALTH_CHECK_ALLOWED_HOSTS`), if live mode will be used through the API.
4. **Auth and rate limiting** before the API is exposed beyond localhost.
5. The license is still "to be decided" in the README.
