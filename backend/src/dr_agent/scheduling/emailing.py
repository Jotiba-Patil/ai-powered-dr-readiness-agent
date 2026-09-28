"""The email after a scheduled run: recipients, facts, send (design sections 7 and 8).

Sending never fails the run: the outcome is recorded as `email_state` (`sent`,
`failed` or `skipped` when nobody could be resolved). A cancelled run gets no email.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dr_agent.models.report import DRReadinessReport
from dr_agent.notify.directory import ContactDirectory
from dr_agent.notify.facts import EmailFacts, report_facts, safe_identifier
from dr_agent.notify.message import build_email
from dr_agent.notify.recipients import (
    RecipientPolicy,
    Recipients,
    RecipientSource,
    resolve_recipients,
)
from dr_agent.notify.senders import Notifier
from dr_agent.scheduling.models import EmailState, RunTrigger, Schedule, ScheduleRun
from dr_agent.scheduling.next_run import describe
from dr_agent.scheduling.source import LoadedInput
from dr_agent.utils.errors import NotificationError

NOT_STORED = "The report could not be saved to the history, so it cannot be executed later."
NO_OWNER = "The runbook owner could not be matched in the contact directory."


@dataclass(frozen=True)
class EmailSettings:
    sender: str
    policy: RecipientPolicy
    ui_base_url: str | None = None


class RunEmailer:
    def __init__(
        self, notifier: Notifier, directory: ContactDirectory, settings: EmailSettings
    ) -> None:
        self._notifier = notifier
        self._directory = directory
        self._settings = settings

    async def send(
        self,
        run: ScheduleRun,
        schedule: Schedule,
        loaded: LoadedInput | None,
        report: DRReadinessReport | None,
    ) -> ScheduleRun:
        owner = loaded.runbook.system_owner if loaded else None
        recipients = await self.recipients(schedule.recipients, owner)
        if not recipients.addresses:
            return run.model_copy(update={"email_state": EmailState.SKIPPED, "email_to": []})
        notes = [NO_OWNER] if recipients.source is RecipientSource.DEFAULT else []
        if report is not None and run.analysis_id is None:
            notes.append(NOT_STORED)
        facts = EmailFacts(
            schedule_name=schedule.name,
            cadence=describe(schedule.cadence, schedule.timezone),
            run_at=run.started_at.astimezone(ZoneInfo(schedule.timezone)),
            manual=run.trigger is RunTrigger.MANUAL,
            service=_service(schedule, loaded, report),
            owner=owner if recipients.owner_found else None,
            report=report_facts(report) if report else None,
            error_code=run.error_code,
            link=self._link(schedule, run),
            notes=notes,
        )
        message = build_email(facts, sender=self._settings.sender, to=recipients.addresses)
        try:
            await self._notifier.send(message)
            state = EmailState.SENT
        except NotificationError:
            state = EmailState.FAILED
        return run.model_copy(update={"email_state": state, "email_to": list(recipients.addresses)})

    async def recipients(self, override: list[str] | None, owner: str | None) -> Recipients:
        """Who a run's email goes to; also used for the form's "Email goes to" preview."""
        return await resolve_recipients(
            override=override,
            owner=owner,
            directory=self._directory,
            policy=self._settings.policy,
        )

    def _link(self, schedule: Schedule, run: ScheduleRun) -> str | None:
        base = self._settings.ui_base_url
        return f"{base}/#/schedules/{schedule.id}/runs/{run.id}" if base else None


def _service(
    schedule: Schedule, loaded: LoadedInput | None, report: DRReadinessReport | None
) -> str:
    if report is not None:
        name = report.service_summary.name
    elif loaded is not None:
        name = loaded.runbook.service_name
    else:
        name = schedule.name
    return safe_identifier(name, fallback="unknown-service")
