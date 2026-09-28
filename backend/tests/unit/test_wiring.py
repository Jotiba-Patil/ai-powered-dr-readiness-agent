import random

import httpx
import pytest
from history_support import MOCK

from dr_agent.config import Settings
from dr_agent.health.live import LiveHealthChecker
from dr_agent.health.mock import MockHealthChecker
from dr_agent.llm.disabled import DisabledProvider
from dr_agent.llm.ollama import OllamaProvider
from dr_agent.llm.openai_compatible import OpenAICompatibleProvider
from dr_agent.notify.directory import EmptyContactDirectory
from dr_agent.notify.senders import LogNotifier, SmtpNotifier
from dr_agent.utils.errors import AnalysisError
from dr_agent.wiring import (
    build_checker,
    build_directory,
    build_llm,
    build_notifier,
    email_settings,
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


async def test_build_llm_ollama_by_default() -> None:
    async with httpx.AsyncClient() as client:
        llm = build_llm(_settings(llm_provider="ollama"), client, random.Random(1))
    assert isinstance(llm, OllamaProvider)


async def test_build_llm_openai_compatible_uses_key_and_format() -> None:
    settings = _settings(
        llm_provider="openai_compatible",
        llm_base_url="https://api.mistral.ai/v1",
        llm_api_key="fake-key",
        llm_response_format="json_object",
    )
    async with httpx.AsyncClient() as client:
        llm = build_llm(settings, client, random.Random(1))
    assert isinstance(llm, OpenAICompatibleProvider)
    assert llm._api_key == "fake-key"
    assert llm._response_format == "json_object"
    assert llm._url == "https://api.mistral.ai/v1/chat/completions"


async def test_build_llm_none_is_disabled_and_raises_analysis_error() -> None:
    async with httpx.AsyncClient() as client:
        llm = build_llm(_settings(llm_provider="none"), client, random.Random(1))
    assert isinstance(llm, DisabledProvider)
    with pytest.raises(AnalysisError, match="disabled"):
        await llm.generate(system_prompt="s", user_prompt="u", schema={})


@pytest.mark.parametrize(
    ("setting", "override", "expected"),
    [(False, None, False), (True, None, True), (False, True, True)],
)
async def test_build_checker_mock_chaos_override(
    setting: bool, override: bool | None, expected: bool
) -> None:
    async with httpx.AsyncClient() as client:
        checker = build_checker(
            _settings(health_check_chaos=setting), client, random.Random(1), chaos=override
        )
    assert isinstance(checker, MockHealthChecker)
    assert checker._chaos is expected


async def test_build_checker_live_uses_timeout_setting() -> None:
    async with httpx.AsyncClient() as client:
        checker = build_checker(
            _settings(health_checker="live", health_check_timeout_ms=1500), client, random.Random(1)
        )
    assert isinstance(checker, LiveHealthChecker)
    assert checker._timeout_seconds == 1.5


def test_build_notifier_by_transport() -> None:
    assert isinstance(build_notifier(_settings()), LogNotifier)
    smtp = build_notifier(_settings(notify_transport="smtp", smtp_host="mailpit", smtp_port=1025))
    assert isinstance(smtp, SmtpNotifier)
    assert (smtp._settings.host, smtp._settings.port) == ("mailpit", 1025)


async def test_build_directory_and_email_settings() -> None:
    assert isinstance(build_directory(_settings()), EmptyContactDirectory)
    contacts = str(MOCK / "contacts.json")
    directory = build_directory(_settings(notify_contacts_file=contacts))
    assert await directory.email_for("Alice Chen") == "alice.chen@example.com"
    email = email_settings(
        _settings(notify_default_email="team@example.com", ui_base_url="http://ui:8080")
    )
    assert (email.sender, email.ui_base_url) == ("dr-agent@example.com", "http://ui:8080")
    assert email.policy.default == "team@example.com"
    assert email.policy.allows("a@example.com")
    assert not email.policy.allows("a@other.org")
