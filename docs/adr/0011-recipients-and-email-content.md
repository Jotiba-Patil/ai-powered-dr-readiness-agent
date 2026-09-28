# 0011. Email recipients from a contact directory; email carries code-computed facts only

- Status: Accepted (2026-09-26)
- Date: 2026-09-26
- Related: [design](../design/scheduled-analysis.md) sections 7, 8 and 13; [ADR 0009](0009-knowledge-base-measured-facts.md) (only measured facts reach prompts)

## Context

After every scheduled run the responsible person gets an email. In the PoC the address may come from configuration. In production the owner named in the runbook should be looked up in a directory tool. The runbook is untrusted input: its owner line and its text can contain anything, including an address the author wants mail sent to, or text written to look like instructions from the organisation. The LLM output built from it is untrusted in the same way. An email from our own system is trusted by its reader, so whatever goes into it needs the same care as a prompt.

## Decision

- Resolve recipients in this order: the schedule's override, then **`ContactDirectory.email_for(owner name)`**, then `NOTIFY_DEFAULT_EMAIL`. If none applies, record `email_state = skipped`.
- The runbook owner is **only a lookup key**. It is never used as an address, even if it looks like one. "Unspecified", "team" and empty owners fall through to the default.
- Every address must pass a simple format check and a domain allow-list (`NOTIFY_ALLOWED_DOMAINS`), with at most 5 recipients per schedule.
- `ContactDirectory` is a protocol. The PoC implementation reads a JSON file (`NOTIFY_CONTACTS_FILE`, `example.com` addresses in `mock-data/contacts.json`). Production directories (LDAP, Entra ID, Okta, PagerDuty/Opsgenie on-call, ServiceNow CMDB) are other implementations, chosen by `NOTIFY_DIRECTORY` in `wiring.py`.
- The email contains **facts computed by code only**: risk score and level, RTO verdict and buffer, gap and SPOF counts, dependency health counts, whether AI analysis was available, the run time and a link to the run. It contains **no runbook text and no LLM text**. Details are one click away in the dashboard.
- Build messages with `email.message.EmailMessage` (rejects CR/LF in headers), and also sanitize and shorten the subject.
- Send through a `Notifier` protocol: `SmtpNotifier` (stdlib `smtplib`, optional STARTTLS, password as `SecretStr`) or `LogNotifier`. A sending failure is recorded on the run and never fails it.

## Consequences

- A prompt-injected runbook cannot put its own text or links into an email, and cannot choose where mail goes.
- The API cannot be used as an open mail relay.
- Emails are short and uniform. Readers who want the reasoning or gap descriptions open the report.
- Moving to a real directory or mail provider means adding an implementation and a config value, with no change to the scheduler.
- Someone has to maintain the contacts file in the PoC, and the domain allow-list in every environment.

## Alternatives considered

- **Use an address written in the runbook.** Simple, but it lets any runbook author direct mail anywhere, and it goes stale when people move.
- **Put the LLM summary in the email.** More useful at a glance, but it carries whatever an injected runbook managed to steer the model to write, under the organisation's own sender.
- **Only a global recipient list.** Works for a demo, but doesn't reach the actual service owner, which was the requirement.
- **A vendor email SDK.** Unnecessary for SMTP. It can be added later as another `Notifier` if a provider API is required.
