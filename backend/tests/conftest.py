"""Every test gets its own database file (ADR 0007) and a fixed display timezone (CLI output)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "dr-agent.db"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DISPLAY_TIMEZONE", "UTC")  # the CLI otherwise shows the machine's zone
    return path
