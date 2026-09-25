"""Snapshot test: format_html output must match backend/tests/fixtures verbatim,
plus targeted checks that untrusted runbook-derived text is escaped, not injected.
"""

from pathlib import Path

from dr_agent.formatters.format_html import format_html
from dr_agent.models.report import DRReadinessReport

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_matches_golden_snapshot(sample_report: DRReadinessReport) -> None:
    expected = (FIXTURES_DIR / "expected_report.html").read_text(encoding="utf-8")
    assert format_html(sample_report) == expected


def test_untrusted_text_is_html_escaped(sample_report: DRReadinessReport) -> None:
    malicious = sample_report.model_copy(
        update={"summary": "<script>alert('xss')</script> looks safe though"}
    )
    output = format_html(malicious)
    assert "<script>" not in output
    assert "&lt;script&gt;" in output
