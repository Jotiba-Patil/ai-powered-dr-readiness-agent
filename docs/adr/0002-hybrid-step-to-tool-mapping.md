# 0002. Hybrid mapping of runbook steps to tool calls

- Status: Accepted (2026-09-24)
- Date: 2026-09-23
- Related: [design](../design/runbook-execution.md) section 4, [ADR 0006](0006-execution-safety-controls.md)

## Context

Runbook steps are free text ("Verify estimate-postgres replica is promoted and accepting writes"). A tool call needs an exact server, tool and argument object. Something has to bridge the two, and whatever does it affects safety, repeatability and how much runbooks must change.

## Decision

Use three tiers, in this order:

1. **Annotated.** A step may declare `Tool:`, `Verify-Tool:` and `Rollback-Tool:` annotations in the format `<server>/<tool> {JSON arguments}` (as nested list items or table columns). They are used as written.
2. **AI-proposed.** For a step without a usable annotation, the LLM proposes one call chosen from the allow-listed tools only. The proposal is badged "AI-proposed", must be explicitly accepted (or edited) by a named reviewer, and then approved like any other call.
3. **Manual.** When neither applies, the step is carried out by a person outside the tool and marked done in the UI or CLI, with an audit event.

All three are untrusted inputs to the same pipeline: allow-list, JSON Schema validation of arguments, policy constraints, risk class, approvals.

## Consequences

- Teams can make runbooks executable gradually: unannotated runbooks still run, with more manual steps and more review.
- Annotated calls are repeatable across drills; AI proposals may differ between runs and are therefore always reviewed.
- The parser gains optional annotation handling; annotation code spans must not be mistaken for validation commands. Existing runbooks and the golden report are unaffected.
- A new executable sample runbook is needed for tests and demos.
- The readiness report could later show how many steps are executable (open question in the design).

## Alternatives considered

- **Annotations only.** Most deterministic, but unannotated runbooks (all existing ones) would be almost entirely manual, which makes the feature hard to adopt.
- **LLM proposes every call.** Least effort for authors, but every call depends on model behavior and is exposed to prompt injection from the runbook text; repeatability suffers.
- **Free-form command strings (the existing validation commands).** Would require a shell tool, which is explicitly excluded.
