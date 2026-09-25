# Architecture Decision Records

Short records of significant decisions: what was decided, why, and what it costs. One decision per file, numbered in order. A record is never rewritten after it is accepted; a later ADR supersedes it instead.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-mcp-python-sdk-client.md) | Use the official MCP Python SDK behind a `ToolExecutor` protocol | Accepted |
| [0002](0002-hybrid-step-to-tool-mapping.md) | Hybrid mapping of runbook steps to tool calls | Accepted |
| [0003](0003-named-approver-two-person-rule.md) | Named approvers with a two-person rule for destructive calls | Accepted |
| [0004](0004-sqlite-execution-store.md) | Durable execution state in SQLite | Accepted; partly superseded by 0007 and 0008 |
| [0005](0005-bundled-mock-mcp-server.md) | Bundled mock MCP server as the only execution target in the PoC | Accepted |
| [0006](0006-execution-safety-controls.md) | Execution safety controls | Accepted |
| [0007](0007-persist-analyses.md) | Persist analyses in the SQLite store, linked to executions | Accepted |
| [0008](0008-store-raw-runbook.md) | Store the raw runbook Markdown with each analysis | Accepted |
| [0009](0009-knowledge-base-measured-facts.md) | Knowledge base from measured facts only, matched by exact identity | Accepted |

Context: 0001-0006 [Design: human-authorized runbook execution via MCP](../design/runbook-execution.md); 0007-0009 [Design: analysis history and DR knowledge base](../design/analysis-history.md).

## Template

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD
- Related: links

## Context
What problem or force makes a decision necessary.

## Decision
What we will do, stated plainly.

## Consequences
What gets easier, what gets harder, what we must now also do.

## Alternatives considered
Each option and why it was not chosen.
```
