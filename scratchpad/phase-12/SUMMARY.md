# Phase 12 summary: history and knowledge-base design (documents only)

Date: 2026-09-25. Status: approved by the project owner on 2026-09-25; ADRs 0007-0009 Accepted.

## Owner decisions (2026-09-25)
- Store every finished analysis, including the raw runbook Markdown, linked to its executions.
- Use the history as a knowledge base for future analyses and recovery.
- Only facts measured by code may reach LLM prompts.
- Design documents first, then build.

## Deliverables
- `docs/design/analysis-history.md`
- `docs/adr/0007-persist-analyses.md`, `0008-store-raw-runbook.md`, `0009-knowledge-base-measured-facts.md` (Proposed); ADR index updated
- `docs/IMPLEMENTATION_PLAN.md`: Phases 12-14; README roadmap; phase list in `.claude/skills/phase-workflow/SKILL.md`

No code changed, so the test and lint gate was not rerun.

## Assumptions made in the design (open for review)
| # | Assumption | Why |
|---|---|---|
| P12-1 | One SQLite file for analyses and executions; setting renamed `DB_PATH`, `EXECUTION_DB_PATH` kept as fallback | Real foreign key; history works with execution off |
| P12-2 | Analysis id = job id | `analysisJobId` in the API keeps working |
| P12-3 | Only successful analyses are stored | Failed jobs have no report |
| P12-4 | Saving failures never fail the analysis (`historySaved: false`) | Storage must not break the core feature |
| P12-5 | CLI saves by default, `--no-save` to skip | Same behaviour as the API; `execute` needs the record |
| P12-6 | Keep forever by default; `HISTORY_RETENTION_DAYS` optional; analyses with executions cannot be deleted | Audit trail must keep its source |
| P12-7 | Re-executing an old analysis is allowed, with a warning after 24 h | Dependency health may have changed |
| P12-8 | Knowledge base uses live executions only | Dry runs measure nothing real |
| P12-9 | Exact step fingerprint (normalized action + target system), no embeddings | Deterministic; no false merges |
| P12-10 | History findings are a new `GapType.HISTORICAL` that feeds the existing risk scoring | Keeps one scoring path; golden report unchanged without history |
| P12-11 | No encryption at rest, no per-user access (PoC) | No authentication or key management yet; documented |

## Follow-up
Phase 13 (analysis history) and Phase 14 (knowledge base) were built on 2026-09-25; differences from this design are in design sections 13 and 14 and in `scratchpad/phase-13/SUMMARY.md` and `scratchpad/phase-14/SUMMARY.md`.
