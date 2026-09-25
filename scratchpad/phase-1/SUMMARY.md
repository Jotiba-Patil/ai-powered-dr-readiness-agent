# Phase 1 Summary: Foundation

Date: 2026-09-21. Status: **Done** (CI workflow not run remotely, see Caveats).

## Phase 0 validation (done first)
Phase 0 was checked against the machine and the raw spike results before starting.
- uv 0.12.10, Python 3.12.14 (via uv), Node 26.1.0 present. Ollama 0.34.2 installed with `qwen2.5:7b-instruct` and `qwen2.5:3b-instruct` pulled. `make` and Docker absent, as recorded.
- Every figure in `phase-0/SUMMARY.md` matches `phase-0/results/*.json` (4 of 4 schema-valid, 5.0 to 5.3 tok/s for 7B, 131 to 143 s per call, no OWNER_AMBIGUITY or NO_VALIDATION found by either model).
- One fix: the summary said the 3B load time was "not recorded"; the results file has 8.3 s. Corrected.
- Note: `ollama` is not on the bash PATH (installed at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`). Relevant to Phase 4 tooling, not to the app, which talks HTTP.

## What was built
| Area | Files |
|---|---|
| Project | `pyproject.toml` (uv, ruff, mypy strict, pytest, poethepoet), `.python-version` (3.12), `.env.example`, `.gitignore`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` |
| Config | `backend/src/dr_agent/config.py`: pydantic-settings, frozen, fail fast with `ConfigError` listing every bad variable |
| Errors | `utils/errors.py`: `AppError` -> `ParseError`, `ValidationError`, `AnalysisError`, `ConfigError`, each with a stable `code` and `to_dict()` in the shared `{error, code, details?}` shape |
| Logging | `utils/logging.py`: structlog JSON, request/correlation id via contextvars, secret redaction processor |
| Timing | `utils/timing.py`: `Stopwatch` and `timed()` with injectable clock |
| Models | `models/base.py` (camelCase JSON, `extra="forbid"`), `runbook.py`, `inventory.py`, `report.py` |
| Tests | `backend/tests/unit/` (6 files, 91 tests) |

Empty package skeletons exist for `core/`, `health/`, `llm/`, `api/` so later phases add files, not structure.

## Decisions and assumptions
| # | Decision | Reason |
|---|---|---|
| P1-1 | Python attributes are snake_case, JSON is camelCase (`alias_generator=to_camel`), so reports match the brief exactly | Brief schema is camelCase; Python style is snake_case |
| P1-2 | `extra="forbid"` on all models | Unknown fields from files or LLM output fail loudly |
| P1-3 | `riskLevel` is a computed field: LOW 0-25, MEDIUM 26-50, HIGH 51-80, CRITICAL 81-100. Thresholds are my choice; the brief only says "derived from score". The CRITICAL cut matches the CLI exit-code rule (score above 80) | Needed a concrete mapping |
| P1-4 | A serialized report can be re-validated: an incoming `riskLevel` is accepted only if it matches the score | Golden-report and round-trip tests |
| P1-5 | `riskScore` is strict int (rejects `true`, `4.5`, `"80"`) | Found by a test: Pydantic lax mode turned `true` into 1. Strictness lets a bad LLM value trigger the Phase 4 correction retry |
| P1-6 | `Runbook` validates step numbers are unique and `dependsOn` refers to existing, other steps | Phase 0's 3B run produced self-dependencies; catch them at the model |
| P1-7 | Inventory gets `mockStatus` (default UP) and `mockLatencyMs`; `ServiceStatus` is UP/DOWN/UNREACHABLE while `DependencyStatus` adds NOT_IN_INVENTORY | Per plan Phase 3 note and brief's two status vocabularies |
| P1-8 | Report gains `aiAnalysisAvailable` and `aiNote` (note required when unavailable) | Supports the graceful-degradation requirement; small addition beyond the brief schema |
| P1-9 | Runbook `rpoMinutes` must be > 0, as the brief says "positive" | Real RPO 0 (sync replication) would need a parser default or a schema change; revisit in Phase 2 |
| P1-10 | `statedRTO`/`statedRPO` in the report are minutes (brief did not say) | Consistent with the rest of the schema |
| P1-11 | `dev-api` poe task and vitest in `poe test` are deferred to Phase 5 and 6 | No FastAPI or frontend exists yet; a task that always fails is worse than none |

## Exit criteria
| Criterion | Result | Evidence |
|---|---|---|
| Models unit-tested | Done | 91 tests pass; models, config, errors, logging, timing at 100% line and branch coverage |
| Coverage above 80% | Done | 100.00% total (307 statements, 36 branches) |
| Lint clean | Done | `uv run poe lint`: ruff check, ruff format --check, `mypy --strict` (15 source files) all pass |
| Files under 200 lines | Done | Largest source file `report.py` at 146 lines, largest test 183 |
| No `Any`, no bare `except` | Done | grep clean; only `AnyHttpUrl` (Pydantic type) matches |
| `core/` and `health/` framework-free | Done (trivially, empty) | `test_package.py` scans sources for FastAPI/Typer/Rich imports so it guards later phases |
| CI skeleton green | Partial | `.github/workflows/ci.yml` runs the same two commands (`poe lint`, `poe test`) that pass locally. It has not run on GitHub: this directory is not a git repository |

## Caveats and follow-ups
- Not a git repo, so `pre-commit install` was not run and the CI workflow has never executed. Run `git init` and `uv run pre-commit install` when ready.
- `uv.lock` was generated; commit it (CI uses `uv sync --frozen`).
- mypy checks `backend/src` only. Tests are linted by ruff but not type-checked.
- `.gitignore` excludes `.claude/settings.local.json` (personal). Remove that line if the team wants it shared.
- Phase 2 will add runtime dependencies as needed (`markdown-it-py` first); only `pydantic`, `pydantic-settings`, `structlog` are installed now.

## Commands verified
```
uv sync
uv run poe format
uv run poe lint     # ruff + format check + mypy --strict
uv run poe test     # pytest --cov, fail under 80%
```
