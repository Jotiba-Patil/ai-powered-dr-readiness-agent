import pytest

from dr_agent.api import __main__ as api_main


def test_main_serves_app_with_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setenv("API_HOST", "0.0.0.0")  # noqa: S104 -- asserted value only, nothing binds
    monkeypatch.setenv("LOG_LEVEL", "warning")
    seen: dict[str, object] = {}

    def fake_run(app: object, **kwargs: object) -> None:
        seen.update(kwargs, app=app)

    monkeypatch.setattr(api_main.uvicorn, "run", fake_run)
    assert api_main.main() == 0
    assert (seen["host"], seen["port"], seen["log_level"]) == ("0.0.0.0", 8123, "warning")  # noqa: S104
    assert seen["timeout_graceful_shutdown"] == 10


def test_main_exits_1_on_invalid_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PORT", "not-a-port")
    assert api_main.main() == 1
    assert "CONFIG_ERROR" in capsys.readouterr().err
