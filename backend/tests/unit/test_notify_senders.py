"""Email senders: SMTP (fake client for every branch, one real loopback exchange) and log."""

from __future__ import annotations

import smtplib
import socket
from email.message import EmailMessage
from types import TracebackType
from typing import ClassVar

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Message
from pydantic import SecretStr

from dr_agent.notify.senders import LogNotifier, SmtpNotifier, SmtpSettings
from dr_agent.utils.errors import NotificationError


def message(to: str = "a@example.com") -> EmailMessage:
    email = EmailMessage()
    email["Subject"] = "[DR readiness] svc: LOW risk (10/100)"
    email["From"] = "dr-agent@example.com"
    email["To"] = to
    email.set_content("hello")
    return email


class FakeSMTP:
    instances: ClassVar[list[FakeSMTP]] = []
    fail_with: ClassVar[Exception | None] = None
    refused: ClassVar[dict[str, tuple[int, bytes]]] = {}

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.args = (host, port, timeout)
        self.calls: list[str] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        if FakeSMTP.fail_with is not None:
            raise FakeSMTP.fail_with
        return self

    def __exit__(
        self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.calls.append("quit")

    def starttls(self, context: object) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, email: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self.calls.append(f"send:{email['To']}")
        return FakeSMTP.refused


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances, FakeSMTP.fail_with, FakeSMTP.refused = [], None, {}
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


async def test_plain_smtp_send(fake_smtp: type[FakeSMTP]) -> None:
    await SmtpNotifier(SmtpSettings("mailpit", 1025, 5.0)).send(message())
    [client] = fake_smtp.instances
    assert client.args == ("mailpit", 1025, 5.0)
    assert client.calls == ["send:a@example.com", "quit"]


async def test_starttls_and_login(fake_smtp: type[FakeSMTP]) -> None:
    settings = SmtpSettings("relay", 587, 5.0, True, "dr-agent", SecretStr("s3cret"))
    await SmtpNotifier(settings).send(message())
    assert fake_smtp.instances[0].calls[:2] == ["starttls", "login:dr-agent:s3cret"]
    assert "s3cret" not in repr(settings)


@pytest.mark.parametrize(
    "error", [smtplib.SMTPAuthenticationError(535, b"no"), ConnectionRefusedError(), TimeoutError()]
)
async def test_transport_errors_become_notification_errors(
    fake_smtp: type[FakeSMTP], error: Exception
) -> None:
    fake_smtp.fail_with = error
    with pytest.raises(NotificationError, match=type(error).__name__):
        await SmtpNotifier(SmtpSettings("relay", 25, 1.0)).send(message())


async def test_refused_recipients_are_an_error(fake_smtp: type[FakeSMTP]) -> None:
    fake_smtp.refused = {"a@example.com": (550, b"no such user")}
    with pytest.raises(NotificationError, match="refused 1"):
        await SmtpNotifier(SmtpSettings("relay", 25, 1.0)).send(message())


async def test_log_notifier_keeps_the_last_messages() -> None:
    notifier = LogNotifier(keep=2)
    for index in range(3):
        await notifier.send(message(f"u{index}@example.com"))
    assert [m["To"] for m in notifier.sent] == ["u1@example.com", "u2@example.com"]


class Inbox(Message):
    def __init__(self) -> None:
        super().__init__()
        self.received: list[str] = []

    def handle_message(self, message: object) -> None:
        self.received.append(str(message))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def test_real_smtp_exchange_on_loopback() -> None:
    inbox = Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=free_port())
    controller.start()
    try:
        settings = SmtpSettings("127.0.0.1", controller.port, 5.0)
        await SmtpNotifier(settings).send(message("alice.chen@example.com"))
    finally:
        controller.stop()
    [raw] = inbox.received
    assert "To: alice.chen@example.com" in raw
    assert "Subject: [DR readiness] svc: LOW risk (10/100)" in raw
