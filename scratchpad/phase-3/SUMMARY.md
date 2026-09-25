# Phase 3 Summary: Health Validator and Mock Inventories

Date: 2026-09-22. Status: **Done**.

## Phase 0/1/2 validation (done first)
Re-ran the full gate before starting: `uv run poe lint` (ruff check, ruff
format --check, mypy --strict) and `uv run poe test` — both green, 151 tests,
99% coverage, matching `scratchpad/phase-2/SUMMARY.md` exactly. Cross-checked
`docs/IMPLEMENTATION_PLAN.md` and `README.md` against the actual repo state;
both already reflected Phase 0-2 as done.

## What was built
| Area | Files |
|---|---|
| Dependency | `httpx` added (`pyproject.toml`, `uv.lock`) |
| Interface | `health/base.py`: `HealthChecker` Protocol, `check_all(services) -> list[ServiceStatus]` |
| Mock checker | `health/mock.py`: `MockHealthChecker` — reads `InventoryService.mock_status`, synthesizes 50-200ms latency (or uses `mockLatencyMs` if set), optional `chaos` flag with a configurable failure rate (default 20%) that overrides the result to `UNREACHABLE`. RNG and the sleep function are both injected. |
| Live checker | `health/live.py`: `LiveHealthChecker` — real HTTP GET over an injected `httpx.AsyncClient`; 2xx -> UP, other response -> DOWN, timeout/transport error -> UNREACHABLE. `asyncio.gather(..., return_exceptions=True)` as a safety net for any exception `_check_one` doesn't already catch. |
| Cross-match | `health/dependency_check.py`: `check_dependencies(runbook, inventory, checker) -> list[DependencyHealth]` — matches `Runbook.dependencies` to `SystemInventory.services` case-insensitively, calls the injected checker only for matched services, and returns `NOT_IN_INVENTORY` for the rest. `impact` is computed deterministically from which steps reference the dependency name in their target system, action text or validation command. |
| Mock inventories | `mock-data/inventories/{healthy,partial-outage,major-outage}.json`, 7 services each: `estimate-postgres`, `pricing-cache`, `rates-kafka-topic`, `internal-dns`, `payment-ledger-db`, `fraud-check-external`, `legacy-token-vault` |
| Tests | 5 new test files, 34 new tests (185 total), 99.09% coverage; `health/` package itself at 100% |

## Design decisions
| # | Decision | Reason |
|---|---|---|
| P3-1 | `HealthChecker.check_all` takes the whole batch and returns results in input order, rather than one-service-at-a-time | Matches the brief's `Promise.allSettled`-style parallel check; lets `MockHealthChecker` and `LiveHealthChecker` each own their own `asyncio.gather` call, and lets `dependency_check.py` call the checker exactly once per `check_dependencies` invocation |
| P3-2 | `MockHealthChecker` takes an injected `random.Random` and an injected async `sleeper` (default `asyncio.sleep`), never constructs either itself | Rule: "Dependencies (health checker, LLM provider, clock, RNG) are passed in, never constructed inside core functions." Also required for `testing.md`'s "no sleeps, no wall-clock, no random without a seed" — tests pass a no-op sleeper and a seeded `Random`, so the whole suite runs in milliseconds |
| P3-3 | Chaos determinism is tested by running two independently-constructed checkers seeded with the same integer and asserting identical output, rather than hand-deriving expected float thresholds | Hand-computing `random.Random(seed).uniform(...)`/`.random()` draw sequences across concurrently-scheduled coroutines is fragile to reason about and brittle to internal asyncio scheduling details; same-seed-same-output is the actual guarantee that matters and needs no such assumption |
| P3-4 | `LiveHealthChecker` takes an injected `httpx.AsyncClient`, never builds one | Same DI rule as P3-2; tests use `httpx.MockTransport` so no real network call is ever made, per `testing.md` |
| P3-5 | Response semantics: any 2xx is UP, any other HTTP response is DOWN, and `httpx.TimeoutException`/`httpx.HTTPError`/anything `gather(return_exceptions=True)` catches is UNREACHABLE | The brief only defines the 4-way status vocabulary; this maps it the way a real health check would (reachable-but-unhealthy vs. unreachable) |
| P3-6 | `check_dependencies` calls the checker only for dependencies that actually match an inventory service, never for the full inventory | Avoids health-checking irrelevant services and keeps `NOT_IN_INVENTORY` a pure name-lookup miss, not a failed check |
| P3-7 | `impact` in the returned `DependencyHealth` is computed now, deterministically, from step text matching (target system / action / validation command), not deferred to the LLM | Phase 4's own plan text says "compute deterministic facts in code (... dependency health ...)"; this is that fact, ready for Phase 4 to embed in the report or enrich further |
| P3-8 | All 3 mock inventories share the same 7 service names, only `mockStatus` differs, with ratios matching the plan text exactly: healthy = all UP, partial-outage = exactly 2 DOWN, major-outage = exactly 4 DOWN + 1 UNREACHABLE (2 stay UP) | Makes the three files directly comparable for Phase 5's CLI demo (same runbook, three inventories, three different reports); matches `docs/IMPLEMENTATION_PLAN.md`'s literal "2/5 down" / "4/5 down + 1 unreachable" phrasing |
| P3-9 | `card-network-gateway` (one of `payment-gateway.md`'s 4 dependencies) is deliberately never listed in any of the 3 inventories | Fulfils the brief's "payment-gateway — one dependency not listed in any inventory" requirement regardless of which inventory it's paired with in a demo |
| P3-10 | Added `S311` to the `backend/tests/**` ruff per-file-ignore, alongside the existing `S101` | `random.Random(seed)` in tests is flagged by bandit's "not cryptographically secure" rule; the seeded RNG here is for deterministic test fixtures, not security, so the finding is a false positive in this context |

## Exit criteria
| Criterion | Result | Evidence |
|---|---|---|
| `HealthChecker` Protocol + `MockHealthChecker` + `LiveHealthChecker` | Done | `health/base.py`, `health/mock.py`, `health/live.py` |
| UP/DOWN/UNREACHABLE/timeout tested | Done | `test_mock_health_checker.py`, `test_live_health_checker.py` |
| Parallelism tested | Done | `test_results_preserve_input_order`, `test_checks_multiple_services_in_order` (both call `check_all` with >1 service through a single `asyncio.gather`) |
| Chaos determinism (seeded RNG) tested | Done | `test_chaos_outcomes_are_deterministic_for_a_given_seed` (parametrized over 3 seeds), `test_chaos_can_turn_an_up_service_unreachable`, `test_chaos_disabled_never_overrides_status` |
| 3 mock inventories created | Done | `mock-data/inventories/*.json`; ratios asserted in `test_mock_inventories.py` |
| Cross-match runbook dependencies to inventory, emit `NOT_IN_INVENTORY` | Done | `health/dependency_check.py`; `test_dependency_check.py` covers UP/DOWN/UNREACHABLE/NOT_IN_INVENTORY, case-insensitive matching, empty-dependencies short-circuit, and `impact` text |
| Coverage above 80% | Done | 99.09% total (790 statements, 202 branches), 185 tests; `health/` package itself 100% |
| Lint clean | Done | `uv run poe lint`: ruff check, ruff format --check, mypy --strict all pass on 28 source files |
| Files under 200 lines | Done | Largest new file `dependency_check.py` at 79 lines |
| `health/` framework-free | Done | `test_package.py` (from Phase 1) still passes unchanged; httpx is an HTTP client, not a web/CLI framework, so it's allowed |
| No `Any`, no bare `except` | Done | grep clean across `health/` |

## Caveats and follow-ups
- `check_dependencies` is not yet wired into a CLI or API entry point — that lands with `analyze_runbook()` in Phase 5, once Phase 4 exists to consume its output.
- `LiveHealthChecker` is authored and unit-tested against `httpx.MockTransport` but has not been exercised against a real endpoint (no live systems exist for this PoC, by design).
- Two genuinely defensive/unreachable branches remain uncovered by design (same trade-off as Phase 2): an owner-label regex producing an empty capture in `metadata_extractor.py`, and `inline_text` on a zero-child node in `text_lines.py`.
- `mock-data/expected-reports/` remains empty; it is a Phase 4 deliverable (golden report for snapshot tests).

## Commands verified
```
uv add httpx
uv run poe format
uv run poe lint     # ruff + format check + mypy --strict
uv run poe test     # pytest --cov, fail under 80% (actual: 99.09%)
```
