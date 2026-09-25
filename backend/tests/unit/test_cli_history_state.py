"""What `dr-agent execute` says about the analysis it follows (stored, stale or neither)."""

from __future__ import annotations

from history_support import make_record
from rich.console import Console

from dr_agent.cli_analysis import CliAnalysis
from dr_agent.cli_execute_view import show_history_state


def _said(analysis: CliAnalysis) -> str:
    console = Console(record=True, width=200)
    show_history_state(console, analysis)
    return console.export_text()


def test_stale_analyses_are_flagged() -> None:
    text = _said(CliAnalysis(make_record(), saved=True, stale=True))
    assert "Analysis a1 is from 2026-09-25 09:00 UTC" in text
    assert "Consider analyzing again" in text


def test_stored_and_unsaved_analyses() -> None:
    assert "Analysis a1 (stored in the history)" in _said(CliAnalysis(make_record(), saved=True))
    assert _said(CliAnalysis(make_record(), saved=False)) == ""
