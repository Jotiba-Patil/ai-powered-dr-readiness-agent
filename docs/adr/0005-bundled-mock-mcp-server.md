# 0005. Bundled mock MCP server as the only execution target in the PoC

- Status: Accepted (2026-09-24)
- Date: 2026-09-23
- Related: [design](../design/runbook-execution.md) sections 3 and 13, [ADR 0001](0001-mcp-python-sdk-client.md)

## Context

The project rule is that all external systems are mocked in the PoC, and that real integrations must only need a different injected implementation. Execution needs something realistic to act on: tools with schemas, state that changes, and failures that can be provoked for drills and tests.

## Decision

- Ship a mock MCP server in `backend/src/dr_agent/mock_mcp/`, built with the SDK's high-level server class, runnable as `python -m dr_agent.mock_mcp` over stdio (local) or streamable HTTP (Docker service `mock-mcp`, internal network only).
- It simulates a small DR environment in memory, keyed by the sample runbooks' systems:

  | Tool | Risk (policy) | Effect |
  |---|---|---|
  | `k8s_rollout_status` | read | Deployment state per region |
  | `k8s_rollout_restart` | write | Restarts a deployment in a region |
  | `k8s_rollout_undo` | write | Rollback for the restart |
  | `db_is_in_recovery` | read | Replica/primary state |
  | `db_promote_replica` | destructive | Promotes the standby replica |
  | `cache_ping` | read | Cache reachable or not |
  | `cache_warm_from_snapshot` | write | Loads a snapshot |
  | `dns_switch_region` | destructive | Points traffic at a region |
  | `smoke_run` | read | Returns pass/fail from current state |

- Tools declare MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`), which the policy may only use to raise a risk class.
- A scenario file (`MOCK_MCP_SCENARIO`) sets initial state and injects failures and latency per tool (for example "`db_promote_replica` fails on the first call"), so drills and tests can exercise failure, rollback and `UNKNOWN` paths deterministically.
- Tests use the SDK's in-memory client against the same server object: no subprocess, no network.
- The default `MCP_SERVERS_FILE` and `EXECUTION_POLICY_FILE` point only at this server.

## Consequences

- End-to-end drills are possible on any machine, safely.
- The mock is a new, small package to maintain, with its own tests.
- Real servers later need their own policy entries and threat review; the engine and UI do not change.
- The mock must not grow into a real simulator; it models only what the sample runbooks need.

## Alternatives considered

- **Fake `ToolExecutor` only, no MCP server.** Enough for engine unit tests, but it would never exercise the real MCP client path, transports or schemas.
- **Real servers in containers (kind cluster, PostgreSQL).** Realistic but heavy, slow in CI and outside the PoC rule.
- **Third-party demo MCP servers.** Their tools do not match DR steps, and we would not control failure injection.
