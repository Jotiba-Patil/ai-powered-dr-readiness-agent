# 0008. Store the raw runbook Markdown with each analysis

- Status: Accepted (2026-09-25)
- Date: 2026-09-25
- Related: [design](../design/analysis-history.md) sections 4.1 and 10; partly supersedes [ADR 0004](0004-sqlite-execution-store.md) ("the runbook text is not stored")

## Context

ADR 0004 stored only a SHA-256 and the parsed plan of a runbook, in line with "never log runbook contents". To reopen, re-analyze or audit an old analysis, the exact text it was based on is needed: the parsed runbook drops wording, and the parser may change. Runbooks can contain hostnames, IP addresses and internal procedures. The project owner chose on 2026-09-25 to store the full text.

## Decision

- Store the raw Markdown (`runbook_markdown`), its SHA-256 and the validated inventory JSON with each analysis. Uploads are already capped by `API_MAX_UPLOAD_BYTES`.
- Treat the database file as sensitive: gitignored, excluded from Docker build contexts, kept on the named volume, documented in the README security notes.
- Serve stored Markdown only as `text/plain` attachment, and show it in the UI as text, never rendered.
- The logging rule is unchanged: runbook text never appears in logs, errors or audit events.

## Consequences

- An old analysis can be reproduced and shown exactly as it was written.
- Anyone who can read the database file, or reach the unauthenticated API, can read every stored runbook. This widens the existing "localhost or authenticating proxy" limit.
- No encryption at rest in the PoC; disk encryption is the recommended mitigation.

## Alternatives considered

- **Parsed runbook plus hash only.** Less sensitive, but an old report can no longer be checked against the text it came from.
- **Encrypt the Markdown column.** Needs key management, which the PoC does not have; revisit with authentication.
- **Store the text outside the database (files).** Splits one record over two places and loses transactional writes.
