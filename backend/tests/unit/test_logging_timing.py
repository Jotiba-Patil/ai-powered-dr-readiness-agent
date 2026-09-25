import json

import pytest
import structlog
from structlog.testing import capture_logs

from dr_agent.utils.logging import (
    REDACTED,
    bind_request_context,
    clear_request_context,
    configure_logging,
    current_context,
    get_logger,
    redact_secrets,
    scrub_url_credentials,
)
from dr_agent.utils.timing import Stopwatch, timed


class FakeClock:
    def __init__(self, *ticks: float) -> None:
        self._ticks = list(ticks)

    def __call__(self) -> float:
        return self._ticks.pop(0)


def test_json_output_with_context_and_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    bind_request_context("req-1")
    try:
        get_logger("t").info("hello", api_key="sk-123", step=2)
        get_logger("t").debug("hidden")
    finally:
        clear_request_context()
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1  # debug filtered out
    record = json.loads(lines[0])
    assert record["event"] == "hello"
    assert record["level"] == "info"
    assert record["request_id"] == "req-1"
    assert record["correlation_id"] == "req-1"
    assert record["api_key"] == REDACTED
    assert record["step"] == 2
    assert "timestamp" in record


def test_unknown_level_falls_back_to_info() -> None:
    configure_logging("nonsense")
    assert get_logger().is_enabled_for(20)  # logging.INFO


def test_explicit_correlation_id_and_clear() -> None:
    bind_request_context("r", "c")
    assert current_context() == {"request_id": "r", "correlation_id": "c"}
    clear_request_context()
    assert current_context() == {}


def test_redact_secrets_leaves_other_keys() -> None:
    out = redact_secrets(None, "info", {"password": "x", "Authorization": "y", "name": "ok"})
    assert out == {"password": REDACTED, "Authorization": REDACTED, "name": "ok"}


def test_stopwatch_uses_injected_clock() -> None:
    watch = Stopwatch(FakeClock(1.0, 1.25))
    assert watch.stop() == pytest.approx(250.0)
    assert watch.stop() == pytest.approx(250.0)  # idempotent, no further clock reads


def test_stopwatch_elapsed_while_running() -> None:
    watch = Stopwatch(FakeClock(0.0, 0.5))
    assert watch.elapsed_ms == pytest.approx(500.0)


def test_timed_logs_duration() -> None:
    structlog.reset_defaults()
    clock = FakeClock(0.0, 0.1, 0.1)
    with capture_logs() as logs, timed(get_logger(), "parse", clock=clock) as watch:
        pass
    assert watch.elapsed_ms == pytest.approx(100.0)
    assert logs == [{"event": "parse", "log_level": "debug", "duration_ms": 100.0}]


def test_timed_without_logger_and_on_error() -> None:
    with pytest.raises(RuntimeError), timed(clock=FakeClock(0.0, 1.0)) as watch:
        raise RuntimeError("x")
    assert watch.elapsed_ms == pytest.approx(1000.0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GET http://user:pw@host:11434/api", "GET http://***@host:11434/api"),
        (
            "https://token@example.com and ftp://a:b@c/d",
            "https://***@example.com and ftp://***@c/d",
        ),
        ("no url here, mail@example.com", "no url here, mail@example.com"),
        ("http://host/path?q=a@b", "http://host/path?q=a@b"),
    ],
)
def test_scrub_url_credentials(text: str, expected: str) -> None:
    assert scrub_url_credentials(text) == expected


def test_redact_secrets_scrubs_urls_in_string_values() -> None:
    event = redact_secrets(None, "info", {"event": "x", "url": "http://u:p@h/", "count": 3})

    assert event == {"event": "x", "url": "http://***@h/", "count": 3}


def test_logged_tracebacks_are_scrubbed(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    try:
        raise RuntimeError("failed for url 'http://admin:hunter2@ollama:11434/api/chat'")
    except RuntimeError:
        get_logger("t").exception("boom")

    line = capsys.readouterr().out
    assert "hunter2" not in line
    assert "http://***@ollama:11434" in line
