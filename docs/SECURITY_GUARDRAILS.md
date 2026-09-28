# Security guardrails

How the DR Readiness Agent protects against prompt injection and other threats. The basic rule is that **all runbook text, stored history, MCP tool metadata and results, and LLM output are untrusted**. They are validated at the boundary, and nothing an LLM says can make something run without the policy checks and a named human approval.

Related decisions: [ADR 0006](adr/0006-execution-safety-controls.md) (execution safety), [ADR 0003](adr/0003-named-approver-two-person-rule.md) (two-person rule), [ADR 0009](adr/0009-knowledge-base-measured-facts.md) (history in prompts).

## Threat model in brief

| Untrusted source | Main threat | Main controls |
|---|---|---|
| Runbook Markdown (upload, API body, server file) | Prompt injection, oversized input, XSS in reports, path traversal | Escaped delimiters, schema-checked output, size limits, autoescaping, path allow-list |
| LLM responses | Invented facts, malicious tool calls | Pydantic schema, code-computed facts, tool allow-list, human approval |
| MCP tool descriptions and results | Indirect prompt injection, hostile risk hints | Escaped in prompts, never fed back into prompts, hints can only raise risk |
| Stored history | Earlier injected text coming back in new prompts | Allow-list of measured fields only |
| Scheduled-run emails | Injected runbook or model text in a trusted-looking email, mail sent to arbitrary addresses, header injection | Facts-only email, owner name only a directory lookup key, domain allow-list, `EmailMessage` (section 7) |
| Uploaded runbooks (written to disk) | Path traversal, overwriting files, filling the disk, storing unusable or hostile files | One folder inside `API_ALLOWED_DIR`, sanitized name, exclusive create (never overwrite), size and file-count limits, must parse as a runbook, can be turned off (section 7) |
| HTTP clients | Log and header injection, oversized requests, cross-origin calls | ID format check, body limits, CORS allow-list, security headers |

## 1. Prompt injection

### 1.1 The system prompt treats input as data
`backend/src/dr_agent/llm/prompts/system.py`

The system prompt says that everything inside `<runbook>`, `<validation>` and `<history>` is untrusted data supplied by a user. The model must ignore any instructions in it and must never execute or repeat that text as commands. It must answer with a single JSON object only.

### 1.2 Delimiters can't be faked
`backend/src/dr_agent/llm/prompts/analysis.py`

Untrusted text is put into the prompt as JSON, with `<`, `>` and `&` written as JSON unicode escapes (`<`, `>`, `&`). The result is still valid JSON that decodes to the same text, but no tag can appear in it. A runbook therefore can't contain a literal `</runbook>` to close its block and inject instructions after it.

### 1.3 The execution-proposal prompt
`backend/src/dr_agent/llm/prompts/execution.py`

When the model maps an unannotated runbook step to a tool call:
- The step text and tool descriptions are escaped the same way and wrapped in `<step>` and `<tools>`.
- The model only sees **allow-listed** tools.
- The prompt says everything inside the tags is untrusted, tells the model never to invent servers, tools or arguments, and to prefer `{"manual": true}` over a guess.
- A person reviews every proposal before it can be approved.

### 1.4 History only reaches a prompt through an allow-list
`backend/src/dr_agent/knowledge/prompt_facts.py` (ADR 0009)

Stored history reaches a prompt only as code-measured numbers, enum values, timestamps, step numbers and identifiers that already came from the runbook or inventory. Fields are copied one by one, so a field added later can't leak in by accident, and a test checks the allowed key set. Summaries, rationales, reasons, tool results and report text are **never** included. Without this, injected text from an earlier runbook or tool result could reach a later prompt. `KNOWLEDGE_IN_PROMPT=false` turns the history block off completely.

### 1.5 Untrusted output is never fed back in
ADR 0006 §10

Tool results and LLM rationales are stored and shown to reviewers as plain text. They are never put back into a prompt and never used for a decision. Tool results are also validated and truncated (`backend/src/dr_agent/tools/base.py`).

## 2. Validating model output

| Control | Where |
|---|---|
| Every analysis reply is parsed into the `LlmAnalysis` Pydantic model. If it fails validation, it is rejected. | `llm/schemas.py`, `core/analyzer.py` |
| Deterministic facts (RTO feasibility, the four rule-checkable gap types, the fallback risk score) are always calculated in code. If the model is unavailable or its output is invalid, the report uses rule-based results only. | `core/analyzer.py`, `core/rto_analysis.py`, `core/gap_rules.py`, `core/risk_score.py` |
| Proposal replies are validated with length caps (`server` ≤ 64, `tool` ≤ 128, `rationale` ≤ 1000, `reason` ≤ 500 chars). | `llm/proposal_schema.py` |
| A proposal naming a tool that isn't allow-listed is thrown away and the step becomes a manual step. | `execution/proposer.py` |
| `EXECUTION_AI_PROPOSALS=false` turns off AI-proposed calls completely, leaving only runbook annotations. | `config.py` |

## 3. Execution safety

Enforced in `backend/src/dr_agent/execution/` on the server, so the API can't be used to bypass the UI (ADR 0006).

1. **Off by default.** With `EXECUTION_ENABLED=false`, every execution endpoint returns `403 EXECUTION_DISABLED`. With `EXECUTION_ALLOW_LIVE=false`, only dry runs can be created.
2. **Dry run first.** The dry-run executor validates every call and records what would run, without connecting to any server.
3. **Allow-list.** Only tools listed in `EXECUTION_POLICY_FILE` can be proposed, edited in, approved or called. Servers come only from `MCP_SERVERS_FILE`, so a request can never add a new server, command or URL.
4. **Argument validation.** Arguments must pass the tool's `inputSchema` (JSON Schema) and the policy constraints, for example an `enum` of allowed regions. This is checked before approval and again right before the call runs (`execution/policy.py`).
5. **No shell tool.** The policy loader rejects tool names that look like a command runner (`shell`, `bash`, `pwsh`, `cmd`, `exec`, `command`, ...) (`execution/policy_file.py`).
6. **Risk class can only go up.** The risk class comes from the policy. Server hints (`destructiveHint`, `readOnlyHint`) can raise it but never lower it. Verify calls run under the main call's approval, so they must be read-only.
7. **Human approval tied to the call hash.** Each approval records the call's hash, and the engine checks approval again right before running, so an edited call needs a new approval. Destructive calls need **two different people**, and the person who started the execution can't approve a destructive call. Names are case-insensitive (`execution/approvals.py`, ADR 0003).
8. **No automatic retries.** After a restart, calls that were in progress become `UNKNOWN` for a person to resolve.
9. **Limits on each run.** Steps run one at a time, with `EXECUTION_MAX_TOOL_CALLS` (default 50), `EXECUTION_TOOL_TIMEOUT_SECONDS` (default 120), `EXECUTION_MAX_ACTIVE` (default 3) and `EXECUTION_APPROVAL_TIMEOUT_MINUTES` (default 30).
10. **Kill switch.** Abort works in every non-terminal state from the API, CLI and UI. Setting `EXECUTION_ENABLED=false` and restarting stops all execution.
11. **Tamper-evident audit log.** Audit events are hash-chained (`SHA-256(prev_hash || canonical_json(event))`), and `verify_chain()` detects a changed, removed or reordered event (`execution/audit.py`).
12. **Executions always follow an analysis.** There is no standalone way to start an execution. Every execution is created from a finished analysis and follows its plan.

## 4. API and web

| Threat | Control | Where |
|---|---|---|
| Oversized input / memory exhaustion | Request body and uploads capped by `API_MAX_UPLOAD_BYTES` (default 1 MB); declared `Content-Length` checked first; multipart limited to 2 files and 2 fields | `api/body.py`, `config.py` |
| Oversized fields | `max_length` on query, path and body fields (paths 512, names 100–200, comments 500) | `api/routes*.py`, `api/schemas*.py`, `execution/models.py` |
| Path traversal | Server-side paths are resolved (following `..` and symlinks) and must stay inside `API_ALLOWED_DIR` and have an allowed extension. Absolute paths, drive letters and NUL bytes are rejected, and errors show only the path the client sent | `api/paths.py` |
| Log and header injection | `X-Request-ID` and `X-Correlation-ID` accepted only if they match `^[A-Za-z0-9._-]{1,64}$`; otherwise a new ID is generated | `api/middleware.py` |
| XSS in reports | Jinja2 autoescaping is mandatory for the HTML report, and the export route sends a strict CSP | `formatters/format_html.py`, `api/routes.py` |
| Clickjacking, MIME sniffing | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` from the API; nginx adds CSP, `Referrer-Policy: no-referrer` | `api/middleware.py`, `docker/nginx.conf` |
| Cross-origin calls | CORS limited to the `CORS_ORIGINS` list | `api/app.py` |
| Leaking input in errors | Validation errors return the location, message and type only, never the offending input | `loaders.py` |
| Untyped input | All external input (files, API bodies, LLM output) is validated with Pydantic at the boundary | throughout |

## 5. Secrets

- `LLM_API_KEY` and MCP server `env`/`headers` values are Pydantic `SecretStr`, so they never appear in a repr, a log line or an error (`config.py`, `tools/servers_config.py`).
- structlog redacts values whose keys contain `api_key`, `secret`, `password`, `token` or `authorization`, and strips credentials from URLs (`utils/logging.py`).
- The OpenAI-compatible provider also replaces the API key in any error text it passes on (`llm/openai_compatible.py`).
- MCP credentials come only from server configuration. They never appear in tool arguments, API responses, audit events or logs (ADR 0006 §11).
- `.env` is never committed, and `.env.example` holds placeholders only.

## 6. Deployment

`docker-compose.yml`, `docker/`

- Containers run `read_only: true`, with `cap_drop: [ALL]` and `no-new-privileges:true`.
- `mock-mcp` sits on an `internal: true` network with no outbound route and no published port, so only `api` can reach it.
- Uploaded runbooks live on the `dr-agent-uploads` volume at `/app/mock-data/uploads`, the only writable folder in the read-only API image (created in the image, owned by the non-root app user).
- `mailpit` (the PoC inbox for scheduled-run emails) is reachable over SMTP only from `api` on the `internal: true` `mail` network; only its web inbox is published, on `127.0.0.1:8025`.
- The mock MCP HTTP transport accepts only the Host header `mock-mcp:*` (DNS-rebinding protection via MCP `TransportSecuritySettings`).
- CI runs `pip-audit` and `npm audit --audit-level=high` (`uv run poe audit`), and only open-source dependencies are allowed.

## 7. Scheduling and email

`backend/src/dr_agent/scheduling/`, `notify/` (ADR 0010, ADR 0011). The core was built in Phase 16; the API (`/api/v1/schedules`, `/api/v1/scheduler`, `/api/v1/schedule-runs`, all `403 SCHEDULER_DISABLED` while off), the Schedules tab, the CLI and the Mailpit inbox in Phase 17.

| Threat | Control | Where |
|---|---|---|
| The scheduler starting an execution | The scheduler only analyzes and emails. `scheduling/` never imports `execution/`, and a test checks both that and that no execution row appears after a scheduled run. Executions still need a person and the approval flow | `scheduling/runner.py`, `test_scheduling_control.py` |
| Prompt-injected text reaching an inbox | Emails carry code-computed facts only: risk, RTO verdict, counts, a link. No summary, gap descriptions, suggestions or runbook text. The service name is reduced to letters, digits, `.`, `_`, `-`, and the owner's name appears only when the contact directory matched it | `notify/facts.py`, `notify/message.py` |
| A runbook choosing where mail goes | The runbook owner is only a lookup key for the contact directory, never an address, even when it looks like one | `notify/recipients.py` |
| Open mail relay | Every recipient must pass a format check and be in `NOTIFY_ALLOWED_DOMAINS`; at most 5 per schedule | `notify/recipients.py`, `scheduling/models.py` |
| Email header injection | `EmailMessage` rejects CR/LF in headers; the subject is also stripped of control characters and cut to 150 characters. The HTML part is autoescaped | `notify/message.py` |
| Path traversal through a schedule | Runbook and inventory paths go through the same allow-list as `GET /analyze`, when saved and again on every run | `scheduling/source.py` |
| Double runs and bursts | One run per slot (one transaction plus a unique index); a slot missed during downtime runs once; a schedule with a run still going skips the slot; every resume skips missed slots | `scheduling/sqlite_claim.py` |
| SMTP credentials | `SMTP_PASSWORD` is a `SecretStr`, covered by log redaction and never in errors | `notify/senders.py`, `config.py` |
| Runbook uploads | Written only to `API_ALLOWED_DIR/<RUNBOOK_UPLOAD_DIR>` (a single folder name, checked to resolve inside it); `.md` / `.markdown`, UTF-8, `API_MAX_UPLOAD_BYTES`, must parse (`422` otherwise); name reduced to `[a-z0-9-]`, a taken name gets `-2`, `-3`, … (exclusive create, then a temporary file moved over the placeholder, so nothing is ever overwritten); at most `RUNBOOK_UPLOAD_MAX_FILES`; `RUNBOOK_UPLOADS_ENABLED=false` returns `403 UPLOADS_DISABLED`; text never logged | `runbook_uploads.py`, `api/body_upload.py`, `api/routes_samples.py` |
| Report time zone | `?tz=` on the HTML export is validated as an IANA zone (`422` otherwise), never used in a path | `utils/timefmt.py` |
| Mail in the Compose demo | Mailpit is reachable over SMTP only from `api` on the internal `mail` network; only its web inbox is published, on `127.0.0.1:8025` | `docker-compose.yml` |
| Stopping it | Off by default (`SCHEDULER_ENABLED=false`, needs the history); pause, pause until (at most `SCHEDULER_MAX_PAUSE_DAYS`), pause all, cancel a run (no email) | `scheduling/service.py` |

## 8. Development-time guardrails (Claude Code)

These protect the repo while an AI coding agent works on it. They are not part of the product.

- `.claude/hooks/guard_bash.py` blocks broad recursive deletes, force pushes, `git reset --hard`, `git clean -f`, reading `.env`, and `pip install` (use `uv`).
- `.claude/hooks/guard_files.py` blocks edits to `.env`, lock files and the original brief, and blocks writing hardcoded secrets or `Any` types.
- Both hooks let the action through if they fail to parse their input, so they are a convenience rather than a hard control.

## 9. Known gaps (PoC)

| Gap | Risk | Suggested fix before production |
|---|---|---|
| Delimiting and system-prompt instructions reduce injection risk but can't guarantee it | An injected runbook could still skew the model's written findings (summary, risk rationale) within what the schema allows | Keep code-computed facts as the source of truth; label LLM text as AI-generated; optionally add an injection classifier on input |
| No authentication or authorization on the API | Anyone who can reach the API can analyze, read history and approve | Put the API behind SSO/OIDC; use role-based access for approvers |
| Approver names are self-declared | The two-person rule depends on people being honest about who they are | Take approver identity from the authenticated user |
| Anyone who can reach the API can upload runbooks | Bounded by the file-count and size limits, but still disk use and stored content without an owner | Tie uploads to logged-in users; add quotas per user; `RUNBOOK_UPLOADS_ENABLED=false` where not needed |
| Schedule names and "paused by" are self-declared | Until the API has authentication, anyone who can reach it can create, pause or delete schedules | Tie schedule actions to logged-in users; only owners or admins may change a schedule |
| No rate limiting | Repeated analysis requests can use up LLM quota or CPU | Rate-limit per client at the proxy or API layer |
| The audit chain has no external anchor | Someone with database access could rewrite the whole chain | Periodically anchor the chain head in write-once storage |
