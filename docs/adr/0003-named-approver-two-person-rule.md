# 0003. Named approvers with a two-person rule for destructive calls

- Status: Accepted (2026-09-24)
- Date: 2026-09-23
- Related: [design](../design/runbook-execution.md) section 6

## Context

Every tool call must be authorized by a human. The application has no authentication today, and adding an identity provider is a large change on its own. We still need approvals that bind to exactly what runs and that are attributable in the audit log.

## Decision

- An approver identifies themselves by **name** (1-100 characters) with an optional comment. No password or token in the PoC.
- An approval is bound to the **call hash**: SHA-256 of the canonical JSON of `{server, tool, arguments}`. The client must send the hash it was shown; a mismatch is refused (`409 STALE_CALL`). Editing a call removes its approvals, and the engine re-checks the hash immediately before calling.
- Required approvals depend on the tool's risk class from the policy file:
  - `read`: one approval (read-only steps in a phase can be approved together)
  - `write`: one approval
  - `destructive`: two approvals from two different names, neither being the person who started the execution
- Rollback and retry calls need fresh approvals.
- Approvals can be given before an execution starts running, so a team can pre-approve a plan.
- The UI and docs state clearly that identities are not verified.

## Consequences

- Approvals are precise and auditable, and stale approvals cannot be replayed on a changed call.
- Identity is honor-based: anyone with API access can type any name, so the two-person rule protects against mistakes, not against a malicious user. The API must stay on localhost or behind an authenticating proxy, as the README already says for the whole API.
- The approval data model already has an `approver` field, so replacing names with authenticated subjects (OIDC) later changes where the name comes from, not the model.

## Alternatives considered

- **Built-in local accounts and roles.** Real authentication, but passwords, sessions and role management are significant work for a PoC and would still not be SSO.
- **OIDC / SSO now (for example Keycloak).** The right production answer, but it adds a service to deploy and configure; deferred to a later phase.
- **One approval for everything.** Simpler, but destructive actions like promoting a database replica or switching DNS deserve a second pair of eyes.
