---
description: Run the end-to-end demo on the mock data
---

Run the CLI against each mock runbook with the matching inventory and report score, risk level, exit code and any parser warnings:

- estimate-service.md + healthy.json (expect exit 0, low risk)
- payment-gateway.md + partial-outage.json (expect high risk, NOT_IN_INVENTORY dependency)
- auth-service.md + major-outage.json (expect exit 2, critical, RTO infeasible)

Also run with the LLM provider stopped and confirm graceful degradation output.

Then the execution drill: with `EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true`, run `dr-agent execute -r mock-data/runbooks/estimate-service-executable.md --operator Olivia --live` against the default mock server (stdio): it analyzes first and asks; answer `y`, then expect exit 0 and a valid audit chain. For the browser, follow the README's execution drill or run `uv run --with playwright python scratchpad/phase-11/browser_drill.py` with the services it lists.

Then the scheduling drill: with `SCHEDULER_ENABLED=true NOTIFY_TRANSPORT=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1025 NOTIFY_CONTACTS_FILE=mock-data/contacts.json`, an SMTP catcher (`uv run python -u -m aiosmtpd -n -l 127.0.0.1:1025`) and the dashboard, create an hourly schedule for `runbooks/estimate-service.md`, click **Run now**, and expect a succeeded run, an email to alice.chen@example.com with facts only and a link, and `dr-agent schedule list` showing the run. Steps in `scratchpad/phase-17/DRILL.md`. Phase 18 adds: upload a runbook through **Upload runbook…** (point `API_ALLOWED_DIR` at a scratch copy of `mock-data` so the repository stays clean), schedule it monthly, and check that every time reads like `30 Sep 2026, 06:00 UTC+05:30`; see `scratchpad/phase-18/DRILL.md`.

Flag any result that deviates from expectations.
