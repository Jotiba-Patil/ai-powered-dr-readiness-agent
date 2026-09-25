# Phase 8 summary: execution design (documents only)

Date: 2026-09-23. Status: approved by the project owner on 2026-09-24. No code was changed in this phase.

## Goal
Plan how the agent can carry out a runbook's recovery steps through MCP tools with human authorization, before writing any code.

## Decisions confirmed with the project owner
- Target: a bundled mock MCP server only; real servers later through configuration.
- Step to tool call: hybrid. Runbook `Tool:` annotations first, then AI proposals that must be reviewed, otherwise manual steps.
- Approvers: named, not authenticated (PoC); two distinct approvers for destructive calls.
- Documents: design doc plus ADRs.

## Produced
- `docs/design/runbook-execution.md`: goals, architecture and modules, annotation syntax, state machines, approval model, data model and restart recovery, API, CLI, UI, configuration and policy file, security notes, testing, dependencies, rollout.
- `docs/adr/README.md` (index and template) and ADRs 0001-0006.
- `docs/IMPLEMENTATION_PLAN.md`: decision log and Phases 8-11 with exit criteria.
- `README.md`: roadmap rows for Phases 8-11 and links to the design.

## Findings while designing
- The MCP Python SDK's current major version (v2) renamed `FastMCP` to `MCPServer` and offers a single `Client` for stdio, HTTP and in-memory servers. The `ToolExecutor` protocol keeps that choice inside `tools/mcp_executor.py`; the version is pinned at Phase 10.
- `Step.action` already holds the step's free text, so the new fields are `tool_call`, `verify_call` and `rollback_call`.
- The parser already treats code spans in "verify"-style sub-items as validation commands; annotation spans must be excluded from that (noted in Phase 9).
- Existing sample runbooks stay unannotated so the golden report is unaffected; a new executable sample is planned.

## Deviations from the approved plan text
- Annotation format uses `server/tool` instead of `server.tool`, because MCP tool names may contain dots.
- The step state machine adds `AWAITING_MANUAL` (needed for manual steps). The configuration adds `EXECUTION_POLICY_FILE`, `EXECUTION_TOOL_TIMEOUT_SECONDS` and `EXECUTION_MAX_ACTIVE`.

## Exit criteria
- [x] Documents written and cross-linked.
- [x] Project owner approved the design and ADRs on 2026-09-24. The design doc and ADRs 0001-0006 are marked Accepted; Phase 9 started after that.
