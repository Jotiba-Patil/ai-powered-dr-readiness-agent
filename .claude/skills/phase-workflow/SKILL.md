---
name: phase-workflow
description: How to execute one phase of docs/IMPLEMENTATION_PLAN.md end to end with tests and exit-criteria checks. Use when the user asks to implement, continue or finish a phase.
---

# Phase workflow

1. Read the phase section in `docs/IMPLEMENTATION_PLAN.md` and the relevant `.claude/rules/` files.
2. Verify the previous phase exit criteria by running `uv run poe test` and `uv run poe lint`. Stop and report if red.
3. List the files to create or change (each under 200 lines). Note assumptions from the plan's question list that affect this phase.
4. Implement in small steps: models and interfaces first, then implementation, then tests, in the same step.
5. Hooks run ruff on every edit. Fix reported issues immediately rather than batching.
6. Run the full gate: ruff, mypy --strict, pytest with coverage >= 80%, and for UI work eslint and vitest.
7. Report per exit criterion: done, partial, or blocked, with evidence (command output summary). Update checkboxes in `docs/IMPLEMENTATION_PLAN.md` if present.
8. Do not begin the next phase without being asked.

## Phase order
0 decisions and spike, 1 foundation, 2 parser, 3 health validator, 4 LLM analysis and formatter, 5 CLI and API, 6 React dashboard, 7 hardening and delivery, 8 execution design (docs only), 9 execution core, 10 MCP integration, 11 execution API, CLI, UI and delivery, 12 history and knowledge-base design (docs only), 13 analysis history, 14 knowledge base.

Phases 0-14 are done. New work needs a new phase in the plan first.

If `uv run poe ...` fails with `uv trampoline failed to canonicalize script path`, run the same steps via `uv run python -m <tool>` (mypy, pytest, pip_audit, poethepoet) and note it in the phase summary.
