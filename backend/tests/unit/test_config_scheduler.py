"""Scheduler and email settings (Phase 16): off by default, validated at startup."""

import re

import pytest
from test_config import ENV_VARS

from dr_agent.config import load_settings
from dr_agent.utils.errors import ConfigError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_scheduler_defaults() -> None:
    s = load_settings(env_file=None)
    assert s.scheduler_enabled is False
    assert (s.scheduler_tick_seconds, s.scheduler_max_schedules) == (30.0, 50)
    assert (s.scheduler_max_pause_days, s.scheduler_default_timezone) == (90, "UTC")
    assert (s.notify_transport, s.smtp_host, s.smtp_port) == ("log", "localhost", 1025)
    assert (s.notify_from, s.notify_default_email) == ("dr-agent@example.com", None)
    assert s.allowed_email_domains == frozenset({"example.com"})
    assert (s.notify_contacts_file, s.ui_base_url, s.smtp_password) == (None, None, None)


def test_values_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "SCHEDULER_ENABLED": "true",
        "SCHEDULER_DEFAULT_TIMEZONE": "Europe/Berlin",
        "NOTIFY_TRANSPORT": "smtp",
        "SMTP_PASSWORD": "s3cret",
        "SMTP_USERNAME": "  ",
        "NOTIFY_DEFAULT_EMAIL": " dr-team@example.com ",
        "NOTIFY_ALLOWED_DOMAINS": "Example.com, corp.example.org ,,",
        "NOTIFY_CONTACTS_FILE": "",
        "UI_BASE_URL": "http://localhost:8080/",
    }.items():
        monkeypatch.setenv(name, value)
    s = load_settings(env_file=None)
    assert s.scheduler_enabled is True
    assert s.notify_default_email == "dr-team@example.com"
    assert s.allowed_email_domains == frozenset({"example.com", "corp.example.org"})
    assert (s.smtp_username, s.notify_contacts_file) == (None, None)
    assert s.ui_base_url == "http://localhost:8080"
    assert s.smtp_password is not None
    assert "s3cret" not in repr(s)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("SCHEDULER_DEFAULT_TIMEZONE", "Mars/Olympus", "unknown timezone"),
        ("DISPLAY_TIMEZONE", "Mars/Olympus", "unknown timezone"),
        ("NOTIFY_FROM", "not-an-address", "email address"),
        ("NOTIFY_FROM", " ", "is required"),
        ("NOTIFY_DEFAULT_EMAIL", "Team <t@example.com>", "email address"),
        ("UI_BASE_URL", "javascript:alert(1)", "http(s) URL"),
        ("NOTIFY_TRANSPORT", "sendmail", "NOTIFY_TRANSPORT"),
        ("SCHEDULER_MAX_PAUSE_DAYS", "0", "SCHEDULER_MAX_PAUSE_DAYS"),
    ],
)
def test_bad_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_settings(env_file=None)


def test_display_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings(env_file=None).display_zone is None  # the machine's local time
    monkeypatch.setenv("DISPLAY_TIMEZONE", " ")
    assert load_settings(env_file=None).display_zone is None
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Asia/Kolkata")
    zone = load_settings(env_file=None).display_zone
    assert zone is not None
    assert zone.key == "Asia/Kolkata"


def test_scheduler_needs_the_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("HISTORY_ENABLED", "false")
    with pytest.raises(ConfigError, match=r"SCHEDULER_ENABLED: .*HISTORY_ENABLED=true"):
        load_settings(env_file=None)
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    assert load_settings(env_file=None).history_enabled is False
