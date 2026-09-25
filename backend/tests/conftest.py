"""Every test gets its own database file: history is on by default (ADR 0007)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "dr-agent.db"
    monkeypatch.setenv("DB_PATH", str(path))
    return path
