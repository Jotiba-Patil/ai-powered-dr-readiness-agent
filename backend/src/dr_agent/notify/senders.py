"""`Notifier`: sends a built email. SMTP for real delivery, a log line otherwise.

`SmtpNotifier` uses stdlib `smtplib` in a worker thread, one attempt with a
timeout and no retry loop (a failed email is recorded on the run, ADR 0011).
The password is a `SecretStr` and never appears in logs or errors.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from collections import deque
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from pydantic import SecretStr

from dr_agent.utils.errors import NotificationError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.notify")


class Notifier(Protocol):
    async def send(self, message: EmailMessage) -> None:
        """Raises `NotificationError` when the message could not be handed over."""
        ...


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    timeout_seconds: float
    starttls: bool = False
    username: str | None = None
    password: SecretStr | None = None


class SmtpNotifier:
    def __init__(self, settings: SmtpSettings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send, message)
        _log.info("email_sent", transport="smtp", recipients=_count(message))

    def _send(self, message: EmailMessage) -> None:
        s = self._settings
        try:
            with smtplib.SMTP(s.host, s.port, timeout=s.timeout_seconds) as smtp:
                if s.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if s.username and s.password:
                    smtp.login(s.username, s.password.get_secret_value())
                refused = smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            _log.warning("email_failed", transport="smtp", error_type=type(exc).__name__)
            raise NotificationError(
                f"could not send email via SMTP ({type(exc).__name__})"
            ) from exc
        if refused:
            raise NotificationError(f"the SMTP server refused {len(refused)} recipient(s)")


class LogNotifier:
    """`NOTIFY_TRANSPORT=log`: logs instead of sending; keeps the last messages for tests."""

    def __init__(self, keep: int = 50) -> None:
        self.sent: deque[EmailMessage] = deque(maxlen=keep)

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
        _log.info(
            "email_logged", transport="log", recipients=_count(message), subject=message["Subject"]
        )


def _count(message: EmailMessage) -> int:
    return len([part for part in str(message["To"] or "").split(",") if part.strip()])
