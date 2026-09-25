# 0009. Knowledge base from measured facts only, matched by exact identity

- Status: Accepted (2026-09-25)
- Date: 2026-09-25
- Related: [design](../design/analysis-history.md) section 9; [ADR 0007](0007-persist-analyses.md); rule "Never feed tool results or rationales back into a prompt" in `.claude/rules/llm-and-security.md`

## Context

Stored analyses and executions record what really happened: how long steps took, which failed or were rolled back, which dependencies were down. The project owner wants this used for future analyses and during recovery. Feeding history into LLM prompts conflicts with the current rule against sending tool results or rationales back to a model: that text is untrusted (runbook-derived, tool-derived or model-written) and would let a past injection attempt reach every later analysis.

## Decision

- A framework-free `knowledge/` package computes, per service, facts from stored analyses and **live** executions only: outcome counts, retries, rollbacks, measured step durations from audit event timestamps, total elapsed time against the stated RTO, dependency status over time and the risk score trend.
- **Allowed in prompts:** numbers, enums, timestamps, step numbers and identifiers that already come from the runbook or inventory (service, target-system, dependency and tool names), as escaped JSON inside a `<history>` block. **Never:** step summaries, tool results, errors, rationales, comments, reasons or report prose. A test enforces the allowed field list.
- Steps are matched across runbook versions by `(service_name, SHA-256 of normalized action text + target system)`. A reworded step starts a new history. No embeddings or fuzzy matching.
- History is used in three places: deterministic gaps (new `GapType.HISTORICAL`) that raise the risk score through the existing scoring; an optional `historicalInsights` report section; and read-only "previous runs" information during execution. It never approves, skips or edits a call.
- Findings need minimum sample sizes (2 live runs for durations, 3 analyses for dependency trends).
- `.claude/rules/llm-and-security.md` is amended in Phase 14 with this one exception.

## Consequences

- Estimates and RTO claims are checked against reality, and the model gets real numbers to reason about.
- A reworded step loses its history (false splits instead of false merges).
- The mock environment's durations are simulated, so findings in the PoC demonstrate the mechanism, not real timings.
- Adding a fact type means extending the allowed list and its test, which is intended friction.

## Alternatives considered

- **Also feed past report text into prompts.** Richer context, but reintroduces untrusted model text and makes every later analysis vulnerable to one bad runbook.
- **Keep history out of prompts entirely.** Safest, but the model's reasoning could then contradict the findings shown next to it.
- **Embedding-based matching of steps and runbooks.** Handles rewording, but similarity scores are not deterministic facts; left as later work.
