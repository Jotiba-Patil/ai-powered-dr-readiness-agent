"""Snapshot test: render_terminal output must match backend/tests/fixtures verbatim.

If a change intentionally alters the terminal layout, regenerate the fixture
and say so in the PR/commit description rather than editing it blind.
"""

from pathlib import Path

from dr_agent.formatters.format_terminal import render_terminal
from dr_agent.models.report import DRReadinessReport

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_matches_golden_snapshot(sample_report: DRReadinessReport) -> None:
    expected = (FIXTURES_DIR / "expected_terminal_report.txt").read_text(encoding="utf-8")
    assert render_terminal(sample_report) == expected


def test_ai_unavailable_note_is_shown_when_degraded(sample_report: DRReadinessReport) -> None:
    degraded = sample_report.model_copy(
        update={"ai_analysis_available": False, "ai_note": "AI analysis unavailable: timeout"}
    )
    output = render_terminal(degraded)
    assert "AI analysis unavailable: timeout" in output


def test_note_is_hidden_when_ai_analysis_available(sample_report: DRReadinessReport) -> None:
    assert "unavailable" not in render_terminal(sample_report).lower()


def test_no_bottleneck_line_when_rto_is_feasible(sample_report: DRReadinessReport) -> None:
    assert "Bottleneck" not in render_terminal(sample_report)


def test_bottleneck_line_appears_when_rto_is_infeasible(sample_report: DRReadinessReport) -> None:
    infeasible = sample_report.model_copy(
        update={
            "rto_analysis": sample_report.rto_analysis.model_copy(
                update={"feasible": False, "buffer_minutes": -10, "bottleneck_steps": [2]}
            )
        }
    )
    output = render_terminal(infeasible)
    assert "NOT feasible" in output
    assert "Bottleneck steps: 2" in output
