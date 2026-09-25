---
description: Create a new mock runbook plus matching inventory and test case
argument-hint: <service-name> <characteristic, e.g. "vague owners, tight RTO">
---

Create a mock runbook for $ARGUMENTS.

Use the `dr-runbook-parser` skill for the expected format and variations. Add the runbook to `mock-data/runbooks/`, a matching inventory to `mock-data/inventories/` if needed, and a parametrized parser test case. Document the intended gaps in a comment at the top of the runbook so expected findings are clear.
