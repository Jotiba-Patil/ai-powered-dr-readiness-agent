"""Composition root: builds the injected providers from validated `Settings`.

This is the only place that picks concrete `LLMProvider`, `HealthChecker`,
`Notifier` and `ContactDirectory` implementations, so swapping to a real
integration (another LLM backend, live health checks, a mail relay, a contact
directory) means changing config or this file, never `core/`, `health/` or `notify/`.
"""

from __future__ import annotations

import random
from pathlib import Path

import httpx

from dr_agent.config import Settings
from dr_agent.health.base import HealthChecker
from dr_agent.health.live import LiveHealthChecker
from dr_agent.health.mock import MockHealthChecker
from dr_agent.llm.base import LLMProvider
from dr_agent.llm.disabled import DisabledProvider
from dr_agent.llm.ollama import OllamaProvider
from dr_agent.llm.openai_compatible import OpenAICompatibleProvider
from dr_agent.notify.directory import (
    ContactDirectory,
    EmptyContactDirectory,
    StaticContactDirectory,
)
from dr_agent.notify.recipients import RecipientPolicy
from dr_agent.notify.senders import LogNotifier, Notifier, SmtpNotifier, SmtpSettings
from dr_agent.scheduling.emailing import EmailSettings


def build_llm(settings: Settings, client: httpx.AsyncClient, rng: random.Random) -> LLMProvider:
    if settings.llm_provider == "none":
        return DisabledProvider()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(
            client,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            rng=rng,
            api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
            response_format=settings.llm_response_format,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return OllamaProvider(
        client,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        rng=rng,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def build_checker(
    settings: Settings,
    client: httpx.AsyncClient,
    rng: random.Random,
    *,
    chaos: bool | None = None,
) -> HealthChecker:
    """`chaos` overrides `HEALTH_CHECK_CHAOS` when given (the CLI's `--chaos` flag)."""
    if settings.health_checker == "live":
        return LiveHealthChecker(client, timeout_seconds=settings.health_check_timeout_ms / 1000)
    return MockHealthChecker(rng, chaos=settings.health_check_chaos if chaos is None else chaos)


def build_notifier(settings: Settings) -> Notifier:
    """`NOTIFY_TRANSPORT`: `smtp` sends, `log` only logs (ADR 0011)."""
    if settings.notify_transport == "smtp":
        return SmtpNotifier(
            SmtpSettings(
                host=settings.smtp_host,
                port=settings.smtp_port,
                timeout_seconds=settings.smtp_timeout_seconds,
                starttls=settings.smtp_starttls,
                username=settings.smtp_username,
                password=settings.smtp_password,
            )
        )
    return LogNotifier()


def build_directory(settings: Settings) -> ContactDirectory:
    """`NOTIFY_DIRECTORY=static` reads `NOTIFY_CONTACTS_FILE`; production adds more kinds here."""
    if settings.notify_contacts_file is None:
        return EmptyContactDirectory()
    return StaticContactDirectory.from_file(Path(settings.notify_contacts_file))


def email_settings(settings: Settings) -> EmailSettings:
    return EmailSettings(
        sender=settings.notify_from,
        policy=RecipientPolicy(
            allowed_domains=settings.allowed_email_domains,
            default=settings.notify_default_email,
        ),
        ui_base_url=settings.ui_base_url,
    )
