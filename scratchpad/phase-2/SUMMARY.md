# Phase 2 Summary: Markdown Parser and Mock Runbooks

Date: 2026-09-22. Status: **Done**.

## Phase 0/1 validation (done first)
Re-ran the Phase 1 exit gate before starting: `uv run poe lint` (ruff check,
ruff format --check, mypy --strict) and `uv run poe test` both green, 91
tests, 100% coverage — matching `scratchpad/phase-1/SUMMARY.md` exactly.

## What was built
| Area | Files |
|---|---|
| Dependency | `markdown-it-py` added (`pyproject.toml`, `uv.lock`); table support enabled via `.enable("table")`, no extra plugin package needed |
| Parsing core | `core/sections.py` (tree parse + H1/H2 grouping), `core/text_lines.py` (node -> plain-text lines), `core/patterns.py` (regexes, dependency-type keyword map), `core/time_parser.py` (free-text time -> minutes) |
| Extractors | `core/metadata_extractor.py` (owner/RTO/RPO), `core/dependency_extractor.py` (list or table), `core/step_extractor.py` (list-based steps, owner/time/target/validation/dependsOn), `core/step_table_extractor.py` (table-based steps) |
| Orchestrator | `core/parser.py`: `parse_runbook(raw_markdown) -> Runbook`, raises `ParseError` only for empty input, zero recovery steps, or a Runbook that fails Pydantic validation (e.g. duplicate step numbers) |
| Mock runbooks | `mock-data/runbooks/{estimate-service,payment-gateway,auth-service}.md` per the brief's 3 characters |
| Fixtures | `backend/tests/fixtures/{empty,no_headers,malformed,mixed_time_units,table_sections,bullet_steps}.md` |
| Tests | 9 new test files, 60 new tests (151 total), 99% coverage |

## Design decisions
| # | Decision | Reason |
|---|---|---|
| P2-1 | Parse with `markdown-it-py`'s `SyntaxTreeNode` (nested tree, not the flat token stream) | Makes heading-bounded sectioning and list/table traversal straightforward; regex is only applied to the resulting plain-text lines, never to raw markdown |
| P2-2 | GFM tables via `MarkdownIt("commonmark").enable("table")` | The table block rule ships in markdown-it-py core; no `mdit-py-plugins` dependency needed |
| P2-3 | Dependencies and Recovery Steps both accept either a list (bullet/ordered) or a table, detected by node type | Brief and skill both ask for table support; one code path per section handles either shape |
| P2-4 | `ParseError` is raised only for: empty/whitespace-only input, zero extracted recovery steps, or a Runbook that fails its own Pydantic validation (e.g. duplicate/self-referential/unknown `dependsOn`, from Phase 1's `_check_step_graph`) | Matches the skill's "raise only when the Pydantic result is invalid" rule while keeping the Phase 1 `Runbook` model's `steps` field un-constrained (changing it to `min_length=1` would have broken an existing, already-passing Phase 1 test that builds a steps-less `Runbook` directly) |
| P2-5 | Every other missing/malformed field gets a default plus a `parser_warnings` entry, never a raise | Owner -> "Unspecified", RTO/RPO -> 60 min, step time -> 10 min, ambiguous owners like "team"/"TBD" are kept literally (not defaulted) so Phase 4's `OWNER_AMBIGUITY` gap check has something to flag |
| P2-6 | `dependsOn` is only filled from an explicit "after step N[, and step M...]" phrase in the step text; multi-step phrasing ("after step 2 and step 4") is supported | Per skill: "left empty except for explicit phrases"; the AI infers the rest in Phase 4 |
| P2-7 | Dependency name splitting treats `" - "` (spaced hyphen) as a delimiter but never a bare hyphen | Kebab-case service names (`payment-ledger-db`) are the norm; splitting on any hyphen truncated them to their first segment (caught by a test) |
| P2-8 | A table's "estimated minutes" cell is parsed as a bare number first, falling back to unit-text parsing (`"1h 30m"`) only if that fails | A table's numeric column has no unit suffix for `find_minutes`'s regexes to match; found via a fixture test that showed `20`/`15` silently defaulting to 10 |
| P2-9 | Dropped a `try/except ValidationError` around `Dependency` construction in `dependency_extractor.py` that could never actually raise, given the guards already in place | Project rule: don't add error handling for scenarios that can't happen; kept the equivalent guard in the two `Step` builders, where a `0 min` estimate is a real, reachable `ValidationError` (gt=0) |
| P2-10 | Payment-gateway and auth-service mock runbooks were tuned so total step minutes match the brief's numbers exactly (45 min of work vs 30 min RTO; 60 min of work vs 15 min RTO) | Fidelity to `AI-Powered Disaster.md`'s mock-data spec, useful for Phase 4's RTO-feasibility narrative |

## Exit criteria
| Criterion | Result | Evidence |
|---|---|---|
| Parser handles every documented variant (bold/inline-code metadata, table/`Key: value` metadata, bullet/ordered/table dependencies and steps, mixed time units, `@handle`/`(Name)`/`Owner:` owners, nested validation commands, `after step N` dependencies) | Done | `test_metadata_extractor.py`, `test_dependency_extractor.py`, `test_step_extractor.py`, `test_step_table_extractor.py`, `test_sections.py` |
| 3 mock runbooks created matching the brief's 3 characters | Done | `mock-data/runbooks/*.md`; asserted in `test_parser_mock_runbooks.py` (happy path fully populated with no warnings; payment-gateway's 2 "team"-owned steps and tight RTO; auth-service's single-owner bus factor and infeasible RTO) |
| Edge cases covered (empty file, no headers, malformed markdown) | Done | `backend/tests/fixtures/*.md` + `test_parser_edge_cases.py`, `test_parser.py`; empty and no-recovery-steps and duplicate-step-number cases all raise `ParseError` with a descriptive `details` payload instead of crashing |
| Coverage above 80% | Done | 99.00% total (706 statements, 192 branches), 151 tests |
| Lint clean | Done | `uv run poe lint`: ruff check, ruff format --check, mypy --strict all pass on 24 source files |
| Files under 200 lines | Done | Largest new file `step_extractor.py` at 132 lines |
| `core/` framework-free | Done | `test_package.py` (from Phase 1) still passes unchanged |
| No `Any`, no bare `except` | Done | grep clean across `core/` |

## Caveats and follow-ups
- `dependsOn` inference beyond explicit "after step N" phrases is deferred to Phase 4's LLM analysis, as planned.
- The parser does not yet cross-check dependency names against an inventory (`NOT_IN_INVENTORY`) — that is Phase 3's `health/` module, which will consume `Runbook.dependencies`.
- `mock-data/inventories/` and `mock-data/expected-reports/` remain empty; they are Phase 3 and Phase 4 deliverables respectively.
- Two genuinely defensive branches were left uncovered by design rather than padded with contrived tests: an owner-label regex match producing an empty string, and `inline_text` being called on a node with zero children — both are guards against markdown-it-py tree shapes that valid CommonMark output cannot produce.

## Commands verified
```
uv add markdown-it-py
uv run poe format
uv run poe lint     # ruff + format check + mypy --strict
uv run poe test     # pytest --cov, fail under 80% (actual: 99.00%)
```
