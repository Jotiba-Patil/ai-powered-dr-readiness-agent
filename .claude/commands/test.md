---
description: Run the full quality gate and summarize failures
---

Run, in order: `uv run poe lint`, then `uv run poe test`. If a poe task does not exist yet, run the underlying commands (ruff check, ruff format --check, mypy --strict, pytest --cov, and in frontend eslint and vitest).

Summarize: what failed, the root cause for each failure, current coverage percentage against the 80% gate. Fix issues that are clearly in code you changed; report the rest.
