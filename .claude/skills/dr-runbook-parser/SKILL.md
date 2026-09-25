---
name: dr-runbook-parser
description: Conventions for parsing Markdown DR runbooks and writing mock runbooks. Use when working on parser.py, runbook fixtures, or mock-data/runbooks.
---

# DR runbook parsing

## Extraction targets
- H1 gives service name.
- Metadata via bold or inline code labels: `**Owner:**`, `**RTO:**`, `**RPO:**`, also table rows and `Key: value` lines.
- H2 "Dependencies": list or table of name, type, critical flag.
- H2 "Recovery Steps" (or "Procedure", "Steps"): ordered list, bullet list, or table.
- Per step: action, owner (`@handle`, `Owner:`, "(Alice)"), target system, estimated minutes, validation command (inline or fenced code near "verify"/"validate").
- Tool-call annotations (Phase 9, `core/annotations.py`): nested list items `Tool:`, `Verify-Tool:`, `Rollback-Tool:` (a space instead of the hyphen also works) or table columns `Tool`, `Verify Tool`, `Rollback Tool`, each holding one code span `<server>/<tool> {JSON arguments}` (JSON optional, defaults to `{}`). They fill `Step.tool_call`, `verify_call`, `rollback_call`. Annotation items are never taken as validation commands, even though "Verify" matches the validation hint.

## Normalization
- Time: `30 min`, `1h 30m`, `2 hours`, `10-15 min` (use the upper bound and warn), `~45m`. Output integer minutes.
- Owners like "team" or "TBD" are kept literally so gap analysis can flag `OWNER_AMBIGUITY`.
- Dependency type inferred by keyword map (postgres, redis, kafka, vault, dns...) with `other` as fallback.

## Rules
- Parse with markdown-it-py tokens first, regex only as a fallback for semi-structured text.
- Never raise for a missing optional field. Apply a default and append to `parserWarnings`.
- Raise `ParseError` only when the Pydantic result is invalid (for example no steps at all).
- A malformed or duplicate annotation is a parser warning (`step N: Tool annotation ignored: <reason>`), never a `ParseError`. Annotations are untrusted input; the execution policy checks them later.
- Keep existing samples unannotated so the golden report stays valid; add annotations only to dedicated executable samples.
- `dependsOn` is left empty by the parser except for explicit "after step N" phrases. The LLM infers the rest.
- Preserve `rawMarkdown` unchanged.

## Mock runbook catalog
- `estimate-service.md`: happy path, 5 ordered steps, specific owners, RTO achievable.
- `payment-gateway.md`: vague steps, 2 steps owned by "team", one dependency missing from inventory, no validation, RTO 30 vs 45 min of work.
- `auth-service.md`: deprecated service names, one owner for every step, no rollback, RTO 15 vs 60 min, no Dependencies section.
- `order-service.md`: complete reference, every extracted field, 8 steps with health-check `curl` validations and "after step N" ordering, Rollback section, 48 vs 60 min RTO, zero parser warnings. Pairs with `inventories/order-service.json` (all UP) for zero rule gaps.
- `estimate-service-executable.md`: `estimate-service.md` plus tool-call annotations for the `drsim` mock MCP server on every step (5 main, 4 verify, 2 rollback calls), zero parser warnings. Verify calls state their expectation (`expect_ready`, `expect_in_recovery`) because the mock's read tools only fail when told what to expect. Every call must pass the default `execution-policy.json` (`test_default_execution_config.py`). Used by the execution tests; pairs with `inventories/healthy.json`.
