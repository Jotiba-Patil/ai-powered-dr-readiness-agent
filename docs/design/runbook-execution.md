# Design: human-authorized runbook execution via MCP

| | |
|---|---|
| Status | Accepted 2026-09-24 (Phase 8 reviewed by the project owner) |
| Date | 2026-09-23 |
| Phases | 8 (this document, done) and 9-11 (implementation; 9-11 done, see section 17), see [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) |
| Decisions | [ADR index](../adr/README.md): [0001](../adr/0001-mcp-python-sdk-client.md), [0002](../adr/0002-hybrid-step-to-tool-mapping.md), [0003](../adr/0003-named-approver-two-person-rule.md), [0004](../adr/0004-sqlite-execution-store.md), [0005](../adr/0005-bundled-mock-mcp-server.md), [0006](../adr/0006-execution-safety-controls.md) |

## 1. Context

The agent analyzes DR runbooks: it parses steps (`models/runbook.py` `Step`: action text, owner, target system, estimate, validation command, `dependsOn`), groups them into parallel phases (`core/execution_plan.py`) and scores readiness. It never acts.

The next capability is to **carry out the recovery steps through MCP tools, with a human authorizing every call**. That turns a read-only tool into one that changes systems, so safety, auditability and failure handling are the main design drivers, not convenience.

Decisions already made with the project owner:

- Execution targets a **bundled mock MCP server** that simulates a DR environment. Real MCP servers are added later through configuration only.
- Steps become tool calls in a **hybrid** way: a structured `Tool:` annotation in the runbook is used as written; for other steps the LLM may propose a call, which is marked "AI-proposed" and must be reviewed.
- Approvers are **named, without authentication** (proof of concept). Destructive calls need two different people.

## 2. Goals and non-goals

**Goals**
- Turn an analyzed runbook into an executable plan that follows the existing execution phases and step dependencies.
- Show every tool call (server, tool, exact arguments, risk class, origin) to a human before it runs, and run nothing without the required approvals.
- Support a **dry run** (validate and record, call nothing) and a **live** run (call MCP tools).
- Verify each step (verification tool or human confirmation), stop on failure, and offer the step's rollback.
- Keep a durable, tamper-evident audit log of everything that happened and who approved it.
- Survive an API restart without losing state or silently re-running a call.

**Non-goals (PoC)**
- Real infrastructure. Only the mock MCP server is wired by default.
- Authentication or authorization of approvers (see [ADR 0003](../adr/0003-named-approver-two-person-rule.md)).
- Arbitrary shell or command execution. There is no "run command" tool, ever.
- Autonomous execution. The LLM proposes, humans approve; no step runs on the model's say-so.
- Parallel execution of steps within a phase (steps in a phase run one after another in the PoC).
- Multi-tenancy, scheduling, or recurring drills.

## 3. Architecture

```
                 +-------------------+      +---------------------+
 React UI  ----> |  api/             |      |  cli.py             |
 (execution      |  routes_execution |      |  dr-agent execute   |
  view)          +---------+---------+      +----------+----------+
                           |                           |
                           +-------------+-------------+
                                         v
                         +-------------------------------+
                         |  execution/  (framework-free) |
                         |  planner -> engine -> audit   |
                         |  policy, proposer, store      |
                         +---+-----------+-----------+---+
                             |           |           |
                  LLMProvider|  ToolExecutor         |ExecutionStore
                  (existing) |  (injected)           |(injected)
                             v           v           v
                        llm/*     tools/mcp_executor  execution/sqlite_store
                                  tools/dry_run            (SQLite file)
                                         |
                                         | MCP (stdio or streamable HTTP)
                                         v
                              mock_mcp/  (MCPServer, simulated DR environment)
                              ... later: real MCP servers from MCP_SERVERS_FILE
```

The layering rules of the project still apply: `execution/` imports no FastAPI, Typer or Rich; the tool executor, store, LLM provider, clock and ID factory are injected; `wiring.py` is the only place that picks implementations; every file stays under 200 lines.

### 3.1 New modules

| Module | Responsibility |
|---|---|
| `execution/models.py` | Pydantic models: `Execution`, `StepRun`, `ToolCall`, `Approval`, `AuditEvent`; enums `ExecutionState`, `StepState`, `RiskClass`, `CallSource`, `ExecutionMode` |
| `execution/transitions.py` | The step and execution transition tables (section 5) and one `transition()` function that rejects anything not in the table |
| `execution/planner.py` | `Runbook` + phases -> `Execution` with one `StepRun` per step. Reuses `compute_execution_plan()` from `core/execution_plan.py` and the dependency merge used in `core/analyzer.py` (moved to a shared helper). Classifies steps as annotated, proposable or manual |
| `execution/policy.py` | Loads the policy file: allow-listed tools per server, risk class per tool, optional argument constraints. Validates a `ToolCall` (allow-list, JSON Schema of the tool's `inputSchema`, constraints) and returns the approvals it needs |
| `execution/proposer.py` | Asks the LLM for a tool call for an unannotated step and validates the answer (section 4.3) |
| `llm/prompts/execution.py` | The proposal prompt, versioned like `llm/prompts/analysis.py` |
| `execution/approvals.py` | Records approvals, checks the call hash, applies the two-person rule |
| `execution/engine.py` | Drives one execution: picks the next runnable step, calls the tool, verifies, records, pauses on anything that needs a human |
| `execution/audit.py` | Builds hash-chained `AuditEvent`s and verifies a chain |
| `execution/store.py` | `ExecutionStore` protocol |
| `execution/sqlite_store.py` | SQLite implementation (stdlib `sqlite3` through `asyncio.to_thread`), see [ADR 0004](../adr/0004-sqlite-execution-store.md) |
| `tools/base.py` | `ToolExecutor` protocol: `list_tools()` and `call_tool(server, tool, arguments, timeout)` returning a validated `ToolResult` |
| `tools/mcp_executor.py` | MCP SDK client, one connection per configured server, see [ADR 0001](../adr/0001-mcp-python-sdk-client.md) |
| `tools/dry_run.py` | Dry-run executor: validates, records "would call", returns a simulated success, never connects |
| `tools/servers_config.py` | Loads and validates `MCP_SERVERS_FILE` |
| `mock_mcp/` | The bundled mock server (`python -m dr_agent.mock_mcp`), see [ADR 0005](../adr/0005-bundled-mock-mcp-server.md) |
| `api/routes_execution.py`, `api/schemas_execution.py` | HTTP layer (section 8) |
| `cli_execute.py` | `dr-agent execute` (section 9) |

### 3.2 Changes to existing modules

- `models/runbook.py`: `Step` gains optional `tool_call`, `verify_call` and `rollback_call` (type `PlannedToolCall`: server, tool, arguments). Defaults are `None`, so existing runbooks, the analysis and the golden report are unchanged.
- `core/step_extractor.py` and `core/step_table_extractor.py`: recognize the annotations (section 4.1). Annotation code spans are excluded from validation-command extraction.
- `utils/errors.py`: new `AppError` subclasses (section 8.1).
- `config.py`, `wiring.py`, `api/app.py`: settings, builders and lifespan wiring for the store, executor and engine registry.

## 4. From runbook step to tool call

### 4.1 Annotation syntax

A step may carry up to three annotations, each as a nested list item whose text is a label followed by one code span:

```markdown
2. Restart the estimate-service compute nodes in the standby region. **Owner:** Bob Nguyen.
   Target: standby-region-compute. Estimated time: 15 min.
   - Tool: `drsim/k8s_rollout_restart {"deployment": "estimate-service", "region": "standby"}`
   - Verify-Tool: `drsim/k8s_rollout_status {"deployment": "estimate-service", "region": "standby"}`
   - Rollback-Tool: `drsim/k8s_rollout_undo {"deployment": "estimate-service", "region": "standby"}`
```

- Format: `<server>/<tool> <JSON object>`. `server` is a key from `MCP_SERVERS_FILE`; the slash avoids clashing with MCP tool names, which may contain dots. Arguments are a JSON object, so parsing is unambiguous and needs no custom grammar.
- In step tables, optional columns `Tool`, `Verify Tool` and `Rollback Tool` hold the same format.
- An annotation that does not parse produces a parser warning and is ignored; the step then falls back to proposal or manual. Parsing never fails a runbook because of an annotation.
- Annotations are **still untrusted input**. Whoever wrote the runbook chose them, and runbooks come from uploads. They go through the same policy checks and approvals as AI proposals.

A new sample, `mock-data/runbooks/estimate-service-executable.md`, carries annotations for every step. The existing samples are left alone so the golden report stays valid.

### 4.2 Classification

| Step has | Initial handling |
|---|---|
| Valid `Tool:` annotation that passes policy | `AWAITING_APPROVAL`, source `annotated` |
| Annotation that fails policy (unknown tool, bad arguments) | `PROPOSED` with the policy error shown; a human edits it or turns the step into a manual one |
| No annotation, LLM available | Proposal requested -> `PROPOSED`, source `ai_proposed` |
| No annotation, LLM unavailable or it declines | `AWAITING_MANUAL` |

### 4.3 AI proposals

- Input: the step's action, target system and validation command, the step number, and the **allow-listed** tools only (name, description, `inputSchema`). Runbook text and tool descriptions are both untrusted and are embedded as escaped JSON inside delimiters, reusing the escaping of `llm/prompts/analysis.py`.
- Output schema `ToolProposal`: `{ "server", "tool", "arguments", "rationale", "confidence": "low|medium|high" }` or `{ "manual": true, "reason" }`. Validated with Pydantic, with the one correction retry of `llm/parse.py`.
- A proposal naming a tool outside the allow-list, or failing the tool's `inputSchema`, is discarded and the step becomes `AWAITING_MANUAL` with the reason recorded.
- Proposals are **never** approvable as-is without review: the UI requires the reviewer to open the call (`PROPOSED -> AWAITING_APPROVAL` is an explicit "accept proposal" action by a named person, audited).
- The rationale is displayed as plain text and never used for decisions.

## 5. State machines

### 5.1 Step

| From | Event | To |
|---|---|---|
| `PLANNED` | valid annotated call | `AWAITING_APPROVAL` |
| `PLANNED` | proposal ready, or annotation failed policy | `PROPOSED` |
| `PLANNED` | no call possible | `AWAITING_MANUAL` |
| `PROPOSED` | reviewer accepts or edits the call and it passes policy | `AWAITING_APPROVAL` |
| `PROPOSED` | reviewer converts to manual | `AWAITING_MANUAL` |
| `AWAITING_APPROVAL` | required approvals collected | `APPROVED` |
| `AWAITING_APPROVAL` | call edited (all approvals cleared) | `AWAITING_APPROVAL` |
| `AWAITING_APPROVAL` | rejected | `REJECTED` |
| `REJECTED` | call edited / converted to manual | `AWAITING_APPROVAL` / `AWAITING_MANUAL` |
| `APPROVED` | engine starts it (dependencies satisfied, execution `RUNNING`) | `RUNNING` |
| `RUNNING` | tool returned success | `VERIFYING` |
| `RUNNING` | tool error or timeout | `FAILED` |
| `RUNNING` | API restarted or execution aborted mid-call | `UNKNOWN` |
| `VERIFYING` | verify tool succeeds, or a human confirms | `SUCCEEDED` |
| `VERIFYING` | verify tool fails, or a human reports failure | `FAILED` |
| `UNKNOWN` | a human checks the system and reports the outcome | `SUCCEEDED` / `FAILED` |
| `FAILED` | rollback call approved and succeeded | `ROLLED_BACK` |
| `FAILED` | retry requested (fresh approval needed) | `AWAITING_APPROVAL` |
| `AWAITING_MANUAL` | a human reports it done | `MANUAL_DONE` |
| any non-terminal | skipped with a reason | `SKIPPED` |

Terminal: `SUCCEEDED`, `MANUAL_DONE`, `SKIPPED`, `ROLLED_BACK`. A step may start only when every step in its `dependsOn` is `SUCCEEDED`, `MANUAL_DONE` or `SKIPPED` (skips need a reason and are audited). Approvals can be given ahead of time for any step, so a team can pre-approve a whole plan before starting.

### 5.2 Execution

| From | Event | To |
|---|---|---|
| `CREATED` | start | `RUNNING` |
| `RUNNING` | a step needs a human (failure, `UNKNOWN`, approval timeout) or pause requested | `PAUSED` |
| `PAUSED` | resume | `RUNNING` |
| `RUNNING` | every step terminal | `COMPLETED` |
| `RUNNING`, `PAUSED` | operator closes it after an unrecoverable failure | `FAILED` |
| any non-terminal | abort (kill switch) | `ABORTED` |

While `RUNNING`, the engine waits (without pausing) for steps in `AWAITING_APPROVAL`, `PROPOSED` or `AWAITING_MANUAL`. A waiting step that exceeds `EXECUTION_APPROVAL_TIMEOUT_MINUTES` pauses the execution. Aborting cannot cancel a call already sent to a server; that step becomes `UNKNOWN` and must be checked by a human.

The engine never retries a tool call by itself. Transport retries inside `tools/mcp_executor.py` apply only to establishing the connection and listing tools, never to `call_tool`, because recovery actions are usually not idempotent.

## 6. Approval model

See [ADR 0003](../adr/0003-named-approver-two-person-rule.md).

- An approval records approver name, optional comment, time, and the **call hash**: SHA-256 of the canonical JSON of `{server, tool, arguments}` (sorted keys, no whitespace).
- The approve request must send the call hash it was shown. If the call changed in the meantime the request is refused (`409 STALE_CALL`). Editing a call deletes its approvals.
- Required approvals by risk class (from the policy file, section 10):

  | Risk class | Approvals | Constraint |
  |---|---|---|
  | `read` | 1 | Any name; a phase's read-only steps can be approved in one action |
  | `write` | 1 | Any name |
  | `destructive` | 2 | Two different names, neither the person who started the execution |

- Rollback and retry calls need their own approvals, like any other call.
- Names are not authenticated. Anyone who can reach the API can type any name. This is acceptable only for a local PoC and is shown in the UI ("identity not verified"). OIDC is the planned replacement.

## 7. Data model and persistence

See [ADR 0004](../adr/0004-sqlite-execution-store.md).

| Table | Key columns |
|---|---|
| `executions` | `id`, `state`, `mode` (`dry_run` / `live`), `runbook_label`, `runbook_sha256`, `started_by`, `created_at`, `updated_at`, `plan_json` |
| `step_runs` | `execution_id`, `step_number`, `phase`, `state`, `attempt`, `summary` |
| `tool_calls` | `id`, `execution_id`, `step_number`, `kind` (`main` / `verify` / `rollback`), `server`, `tool`, `arguments_json`, `source`, `risk_class`, `call_hash`, `result_json` (truncated to 16 KB), `error`, timings |
| `approvals` | `call_id`, `approver`, `comment`, `call_hash`, `created_at` |
| `audit_events` | `seq`, `execution_id`, `type`, `actor`, `payload_json`, `prev_hash`, `hash`, `created_at` |

- The runbook text itself is not stored, only its SHA-256 and the parsed plan, in line with "never log runbook contents".
- Audit events: `hash = SHA-256(prev_hash || canonical_json(event without hash))`, with a fixed genesis value per execution. `GET .../audit?verify=true` recomputes the chain. The head hash is shown in the UI and included in exports so it can be kept elsewhere; without an external anchor a chain can be rewritten wholesale, which is a documented PoC limit.
- Every state change, approval, edit, proposal, tool call and result is an audit event, written in the same SQLite transaction as the change it describes.
- **Restart recovery:** at startup, any step in `RUNNING` becomes `UNKNOWN` and its execution becomes `PAUSED`, with an audit event. Nothing resumes automatically.
- In Docker the database lives on a named volume (`EXECUTION_DB_PATH=/data/executions.db`), since containers have read-only root filesystems.

## 8. HTTP API

New router `api/routes_execution.py` under `/api/v1`. Bodies and responses are Pydantic models; errors use the shared `{error, code, details?}` shape. All mutating endpoints return the updated execution view. Clients poll `GET /executions/{id}` as they already do for analysis jobs.

| Method and path | Purpose |
|---|---|
| `GET /tools` | Allow-listed tools per server with risk class and input schema (never server credentials) |
| `POST /executions` | Create from a runbook (multipart or JSON, same input rules as `/dr/analyze`); body adds `mode` and `startedBy`. Returns `201` |
| `GET /executions`, `GET /executions/{id}` | List and detail |
| `POST /executions/{id}/start`, `/pause`, `/resume`, `/abort`, `/close` | Execution lifecycle |
| `PUT /executions/{id}/steps/{n}/call` | Replace or accept the step's call (body: call, `editor`); clears approvals |
| `POST /executions/{id}/steps/{n}/approve` | Body: `approver`, `comment?`, `callHash` |
| `POST /executions/{id}/steps/{n}/reject`, `/skip`, `/manual`, `/mark-done`, `/verify`, `/retry`, `/rollback` | Human decisions; each needs `actor` and, where relevant, a reason or outcome |
| `GET /executions/{id}/audit` | Audit log; `?verify=true` adds chain verification |

### 8.1 Errors

| Error | HTTP | Code |
|---|---|---|
| Execution disabled, or live mode not allowed | 403 | `EXECUTION_DISABLED` |
| Transition not allowed from the current state | 409 | `INVALID_TRANSITION` |
| Approval for an outdated call | 409 | `STALE_CALL` |
| Tool not allow-listed, arguments invalid, two-person rule violated | 422 | `POLICY_VIOLATION` |
| Tool call failed (recorded on the step, also returned) | 502 | `TOOL_ERROR` |

CORS keeps `GET` and `POST` and adds `PUT`. The OpenAPI export and generated frontend client are refreshed with `poe gen-api` as today.

## 9. CLI

`dr-agent execute --runbook PATH [--inventory PATH] [--live] --operator NAME`

Runs the same engine in the terminal with an in-process SQLite store (default `./executions.db`). For each step it prints the call as a Rich panel (server, tool, arguments, risk, source) and prompts for approver name(s) or `reject`, `skip`, `manual`, `abort`. Exit codes: `0` completed, `2` failed or aborted, `1` usage or configuration error.

## 10. Configuration and policy

| Variable | Default | Purpose |
|---|---|---|
| `EXECUTION_ENABLED` | `false` | Master switch. When `false`, all execution endpoints return `403` |
| `EXECUTION_ALLOW_LIVE` | `false` | When `false`, only dry runs can be created |
| `EXECUTION_DB_PATH` | `executions.db` | SQLite file |
| `MCP_SERVERS_FILE` | `mcp-servers.json` | MCP servers: `{ "<key>": { "transport": "stdio", "command", "args", "env" } \| { "transport": "http", "url", "headers" } }`; `${VAR}` references are resolved from the environment |
| `EXECUTION_POLICY_FILE` | `execution-policy.json` | Allow-list and risk classes |
| `EXECUTION_APPROVAL_TIMEOUT_MINUTES` | `30` | Waiting time before a step pauses the execution |
| `EXECUTION_TOOL_TIMEOUT_SECONDS` | `120` | Per tool call |
| `EXECUTION_MAX_TOOL_CALLS` | `50` | Upper bound per execution, including verify and rollback calls |
| `EXECUTION_MAX_ACTIVE` | `3` | Executions running at the same time |

Policy file example:

```json
{
  "servers": {
    "drsim": {
      "tools": {
        "k8s_rollout_status": { "risk": "read" },
        "k8s_rollout_restart": { "risk": "write" },
        "db_promote_replica": { "risk": "destructive" },
        "dns_switch_region": { "risk": "destructive",
                               "constraints": { "region": { "enum": ["primary", "standby"] } } }
      }
    }
  }
}
```

A tool not listed is not allowed, even if the server offers it. Tool annotations from the server (`readOnlyHint`, `destructiveHint`) are hints only: if a server marks a tool more dangerous than the policy does, the higher class is used; it is never used to lower one.

## 11. User interface

- The app gets two views, **Analyze** (today's page) and **Execute**, switched by tabs (no router dependency).
- From a finished report: **Start dry run** (and **Start live run** when allowed) prefills the runbook.
- Execution view:
  - Header: runbook, mode badge (`DRY RUN` / `LIVE`), state, started by, audit head hash, **Abort** button (always visible).
  - Phases as groups; each step card shows state, owner, estimate, the call (server, tool, arguments as formatted JSON), risk badge, source badge (`annotated` / `AI-proposed` / `edited`), approvals collected (`1/2`), last result or error.
  - Actions per state: accept/edit call (JSON editor, server-side validation errors shown inline), approve/reject with name and comment, mark manual step done, confirm verification, retry, roll back, skip with reason.
  - Audit panel: chronological events, chain verification result.
- The approver's name is remembered per browser (`localStorage`, convenience only).
- Results and rationales are rendered as text, never as HTML.
- A `useExecution` hook polls like `useAnalysis`.

## 12. Security notes

| Threat | Mitigation |
|---|---|
| Prompt injection through runbook text or tool descriptions steers the LLM toward a harmful call | Allow-list, JSON Schema validation, policy constraints, human sees the exact call, AI proposals badged and never auto-approved, no shell tool |
| Malicious `Tool:` annotation in an uploaded runbook | Treated exactly like an AI proposal: policy + approvals |
| Approving something other than what runs (TOCTOU) | Approval bound to the call hash; edits clear approvals; the engine re-checks the hash before calling |
| Bypassing approvals by calling the API directly | All checks are server-side in `execution/`; the UI has no authority |
| Impersonated approvers | Accepted PoC limit, visible in UI and docs; OIDC later ([ADR 0003](../adr/0003-named-approver-two-person-rule.md)) |
| Audit log tampering | Hash chain, events written in the same transaction as changes, head hash exported |
| Secrets leaking | Server credentials live only in the MCP server config/environment, never in arguments, API responses or logs; existing log redaction applies |
| Tool results carrying instructions | Results are stored and displayed as data; they are never fed back to the LLM |
| Adding arbitrary servers (SSRF, code execution) | Servers only from `MCP_SERVERS_FILE`; requests cannot name new servers or commands |
| Runaway execution | `EXECUTION_ENABLED` and `EXECUTION_ALLOW_LIVE` off by default, max tool calls, per-call timeout, abort, sequential steps |

## 13. Testing strategy

- **Unit:** transition tables (every allowed and a sample of forbidden transitions), policy (allow-list, schema, constraints, risk escalation from hints), approvals (hash binding, two-person rule), audit chain (build, verify, detect tampering), annotation parsing (list and table forms, bad JSON, warnings), proposer with `FakeProvider` (valid, off-list tool, invalid arguments, manual answer).
- **Integration:** engine with the mock MCP server through the SDK's in-memory client and a SQLite file in `tmp_path`: happy path on `estimate-service-executable.md`, injected failure followed by rollback, abort mid-run, restart recovery (`RUNNING` -> `UNKNOWN`).
- **API:** every endpoint, error codes, disabled and dry-run-only modes, stale-hash approval.
- **Frontend:** vitest + React Testing Library for the execution view and hook.
- **End to end:** a scripted drill in the browser through the Playwright MCP: dry run, then live run against the mock server with two approvers, an injected failure, a rollback and an abort.
- Coverage stays above 80%; the existing golden report test must keep passing untouched.

## 14. Dependencies

| Package | License | Why |
|---|---|---|
| `mcp` (official MCP Python SDK) | MIT | Client for MCP servers and the mock server ([ADR 0001](../adr/0001-mcp-python-sdk-client.md)) |
| `jsonschema` | MIT | Validating arguments against each tool's `inputSchema` before approval |

Both are open source and covered by `poe audit`. SQLite is the standard library.

## 15. Rollout

| Phase | Scope | Exit |
|---|---|---|
| 8 | This design and the ADRs | Reviewed and approved |
| 9 | Execution core: models, transitions, policy, approvals, audit chain, SQLite store, dry-run executor, parser annotations | Lint and mypy clean, coverage > 80%, golden report unchanged |
| 10 | MCP integration: `McpToolExecutor`, mock MCP server with fault injection, LLM proposer | Engine runs the executable sample end to end against the mock server in tests, including failure + rollback and restart recovery |
| 11 | API, CLI, UI, Docker (`mock-mcp` service, data volume), docs | Browser drill: dry run, live (mock) run with two approvers, rollback, abort; audit chain verifies |

## 16. Open questions and later work

- OIDC login for approvers and role-based permissions.
- Adapters and policies for real MCP servers (Kubernetes, PostgreSQL, DNS providers), each needing its own threat review.
- Server-sent events instead of polling.
- An "executability" figure in the readiness report (how many steps have validated annotations).
- Parallel execution of independent steps within a phase.
- Anchoring the audit head hash externally (for example in an append-only store).

## 17. Implementation notes (Phase 9)

These points refine the design as built. Details and evidence are in [scratchpad/phase-9/SUMMARY.md](../../scratchpad/phase-9/SUMMARY.md) (P9-1 to P9-10).

- **Verify calls share the main call's approval.** An approval records the hashes of both the main call and the verify call, and a verify call must be a `read` tool. Editing either call clears the approvals.
- **No verify call** means the step waits in `VERIFYING` until a person reports the outcome.
- **Two transitions added to section 5.1:** `APPROVED --edit--> AWAITING_APPROVAL` (also used when the pre-run re-check fails) and `VERIFYING --interrupted--> UNKNOWN` (abort or restart during a verify call).
- **Rollback state lives on the rollback call.** The step stays `FAILED` until the rollback succeeds. A failed rollback, or one whose outcome is unknown, leaves the step `FAILED` with a summary.
- **Storage.** `executions.plan_json` is the source of truth. `step_runs`, `tool_calls` (keyed by execution, step and kind) and `approvals` are projections written in the same transaction. A save whose audit events do not continue the stored chain is refused.
- **Restart recovery** also pauses `RUNNING` executions that have no call in flight.
- **Not built:** approving all read-only steps of a phase in one action (see Phase 11 below).

### Phase 10

Details are in [scratchpad/phase-10/SUMMARY.md](../../scratchpad/phase-10/SUMMARY.md) (P10-1 to P10-9).

- **SDK.** `mcp` 2.2.0 (MIT). `tools/mcp_convert.py` sits next to `tools/mcp_executor.py` and also imports the SDK: it builds clients from config and converts results. `mock_mcp/` uses the SDK's `MCPServer`. A test keeps the SDK out of every other module.
- **Connections** are owned by one background task inside `McpToolExecutor`, because anyio requires a connection to be closed in the task that opened it. Calls can come from any task.
- **Verify calls state their expectation.** A successful MCP call only means the tool ran, so the mock's read tools take optional expectations (`expect_ready`, `expect_in_recovery`) and fail when they are not met. `cache_ping` and `smoke_run` fail on an unhealthy state.
- **AI proposals** are made once, when the execution is created, for every step without an annotation. Unusable answers become manual steps with the reason recorded. Accepting a proposal (edit with no new call) keeps its source `ai_proposed`.

### Phase 11

Details are in [scratchpad/phase-11/SUMMARY.md](../../scratchpad/phase-11/SUMMARY.md) (P11-1 to P11-10).

- **`POST /executions` takes JSON only** (`runbookMarkdown`, `runbookName`, `mode`, `startedBy`), not multipart as section 8 suggested. The dashboard sends text, and the CLI uses the engine directly.
- **Extra endpoint `GET /execution/settings`**: it answers even while execution is off, so a client can explain why, and it carries `approvalsByRisk` so the UI does not hard-code the approval rule.
- **Lifecycle and step decisions are grouped** as `POST /executions/{id}/{action}` and `POST .../steps/{n}/{action}` with typed action names, instead of one route each.
- **Tool calls never run inside a request**, except `rollback`, which runs the approved rollback call within the request so its outcome can be returned. After every other decision the API starts `advance()` in a background task, and a slow ticker (15 s) advances running executions so approval timeouts fire.
- **Dry runs use a dry-run executor built from the connected servers' tool catalog**, so arguments are still checked against the real schemas. The engine picks the executor by the execution's mode.
- **Batch approval of a phase's read-only steps** (ADR 0003) is not built: the UI approves one step per click, which proved enough in the drill.

### After Phase 11: execution follows the analysis

Decided with the project owner on 2026-09-24. This replaces the standalone flow in sections 8, 9 and 11.

- **API:** `POST /executions` takes `{analysisJobId, mode, startedBy}` instead of runbook text. The analysis job must have succeeded (`404` unknown, `409` unfinished or failed). The execution uses the job's parsed runbook and follows its execution plan: each phase waits for the whole previous phase, which reproduces the report's phases, AI-inferred order included. `Execution.analysis` records the job id, risk score and level, AI availability and analysis time, and the `execution_created` audit event carries the same.
- **CLI:** `dr-agent execute` runs the analysis first (with an optional `--inventory`), prints the risk, RTO feasibility, gap count and plan, and asks before executing. `EXECUTION_ENABLED` and `EXECUTION_ALLOW_LIVE` are checked before the analysis starts.
- **UI:** there is no Execute tab (section 11's two views are gone). "Execute this runbook…" under a finished report opens an execution section below it, which warns on HIGH or CRITICAL risk and lists the runs of that analysis.
- **Limit:** analysis jobs are kept in memory, so after an API restart an execution cannot be created from an old analysis (run it again). Existing executions and their audit logs persist as before.
