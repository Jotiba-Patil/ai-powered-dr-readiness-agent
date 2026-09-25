# 0006. Execution safety controls

- Status: Accepted (2026-09-24)
- Date: 2026-09-23
- Related: [design](../design/runbook-execution.md) sections 10 and 12, [ADR 0002](0002-hybrid-step-to-tool-mapping.md), [ADR 0003](0003-named-approver-two-person-rule.md)

## Context

Executing recovery steps can change production systems. Inputs that shape tool calls (runbook text, annotations, LLM output, tool descriptions and results) are all untrusted. The default state of the product must be safe, and the controls must be enforced on the server, not in the UI.

## Decision

1. **Off by default.** `EXECUTION_ENABLED=false`: every execution endpoint returns `403 EXECUTION_DISABLED`. `EXECUTION_ALLOW_LIVE=false`: only dry runs can be created until an operator enables live mode.
2. **Dry run first.** The dry-run executor validates every call against policy and records what would run, without connecting to any server.
3. **Allow-list.** Only tools listed in `EXECUTION_POLICY_FILE` can be proposed, edited in, approved or called. Servers come only from `MCP_SERVERS_FILE`; requests can never name a new server, command or URL.
4. **Argument validation.** Arguments must pass the tool's `inputSchema` (JSON Schema) and any policy constraints (for example an `enum` of allowed regions) before a call can be approved, and again right before it runs.
5. **No shell tool.** There is no generic command or script tool, and the policy loader rejects tool names that suggest one.
6. **Human approval bound to the call hash**, with the two-person rule for destructive tools ([ADR 0003](0003-named-approver-two-person-rule.md)).
7. **No automatic retries of tool calls**, and a restart turns in-flight calls into `UNKNOWN` for a human to resolve.
8. **Blast-radius limits.** Steps run one at a time; `EXECUTION_MAX_TOOL_CALLS` per execution; `EXECUTION_TOOL_TIMEOUT_SECONDS` per call; `EXECUTION_MAX_ACTIVE` executions.
9. **Kill switch.** `Abort` is available in every non-terminal state from the API, CLI and UI. Setting `EXECUTION_ENABLED=false` and restarting stops all execution.
10. **Untrusted output stays data.** Tool results and LLM rationales are stored and shown as text; they are never fed back into a prompt or used for decisions.
11. **Secrets stay in server configuration.** Credentials for MCP servers come from the environment via `MCP_SERVERS_FILE` references; they never appear in arguments, API responses, audit events or logs.

## Consequences

- A fresh install cannot change anything until an operator opts in twice (enable, then allow live).
- Operators must maintain a policy file; unlisted tools are unusable even when a server offers them.
- Some friction during a real incident (approvals, sequential steps) is accepted in exchange for safety; pre-approval of a plan reduces it.
- Every control needs tests that try to bypass it through the API directly.

## Alternatives considered

- **Trust server annotations for risk.** Annotations are hints from the server and may be wrong or hostile; they may only raise a risk class.
- **Deny-list of dangerous tools.** Fails open for anything new; an allow-list fails closed.
- **UI-only confirmations.** Trivially bypassed by calling the API; all checks live in `execution/`.
