---
description: Implement one phase from the plan (usage: /phase 2)
argument-hint: <phase number 0-7>
---

Implement Phase $ARGUMENTS from `docs/IMPLEMENTATION_PLAN.md`.

1. Use the `phase-workflow` skill.
2. Confirm the previous phase's exit criteria are met. If not, stop and say what is missing.
3. Restate the phase scope and any assumptions in a few lines, then implement it with tests alongside the code.
4. Run `uv run poe lint` and `uv run poe test`. Fix failures.
5. Report exit-criteria status per item and what remains. When done, mark the phase DONE in `docs/IMPLEMENTATION_PLAN.md` and the README roadmap, and write `scratchpad/phase-N/SUMMARY.md`. Do not start the next phase.
