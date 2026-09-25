---
description: Review the current phase's code against the plan and project rules
argument-hint: <phase number>
---

Review the code for Phase $ARGUMENTS against `docs/IMPLEMENTATION_PLAN.md`, `CLAUDE.md` and `.claude/rules/`.

Check: exit criteria, no `Any`, files under 200 lines, no framework imports in `core/` and `health/`, Pydantic validation at all boundaries, typed errors, tests present and deterministic, no secrets or real network calls. Report findings ordered by severity with file and line, and do not change code.
