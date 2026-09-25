---
description: Run the end-to-end demo on the mock data
---

Run the CLI against each mock runbook with the matching inventory and report score, risk level, exit code and any parser warnings:

- estimate-service.md + healthy.json (expect exit 0, low risk)
- payment-gateway.md + partial-outage.json (expect high risk, NOT_IN_INVENTORY dependency)
- auth-service.md + major-outage.json (expect exit 2, critical, RTO infeasible)

Also run with the LLM provider stopped and confirm graceful degradation output.

Then the execution drill: with `EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true`, run `dr-agent execute -r mock-data/runbooks/estimate-service-executable.md --operator Olivia --live` against the default mock server (stdio): it analyzes first and asks; answer `y`, then expect exit 0 and a valid audit chain. For the browser, follow the README's execution drill or run `uv run --with playwright python scratchpad/phase-11/browser_drill.py` with the services it lists.

Flag any result that deviates from expectations.
