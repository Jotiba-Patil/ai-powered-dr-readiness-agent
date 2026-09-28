"""Email content: facts only, safe subject, escaped HTML, failure emails."""

from __future__ import annotations

from datetime import UTC, datetime
from email import message_from_string, policy
from zoneinfo import ZoneInfo

import pytest
from history_support import golden_report

from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import Severity
from dr_agent.notify.facts import EmailFacts, report_facts, safe_identifier
from dr_agent.notify.message import MAX_SUBJECT, build_email, plain_text, subject

RUN_AT = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)


def facts(**update: object) -> EmailFacts:
    base = EmailFacts(
        schedule_name="Estimate <b>daily</b>",
        cadence="Daily 06:00 UTC",
        run_at=RUN_AT,
        manual=False,
        service="Estimate-Service",
        owner="Alice Chen",
        report=report_facts(golden_report()),
        link="http://localhost:8080/#/schedules/s1/runs/r1",
    )
    return EmailFacts(**{**base.__dict__, **update})


def test_report_facts_count_by_severity_and_status() -> None:
    report = golden_report()
    counted = report_facts(report)
    assert sum(counted.gaps.values()) == len(report.gap_analysis)
    assert set(counted.gaps) == set(Severity)
    assert sum(counted.dependencies.values()) == len(report.dependency_health)
    assert set(counted.dependencies) == set(DependencyStatus)


def test_subject_for_success_and_failure() -> None:
    report = golden_report()
    level, score = report.risk_level.value, report.risk_score
    assert subject(facts()) == f"[DR readiness] Estimate-Service: {level} risk ({score}/100)"
    at_risk = facts(
        report=report_facts(
            report.model_copy(
                update={"rto_analysis": report.rto_analysis.model_copy(update={"feasible": False})}
            )
        )
    )
    assert subject(at_risk).endswith(", RTO at risk")
    assert subject(facts(report=None, error_code="PARSE_ERROR")).endswith(
        "scheduled analysis failed"
    )


def test_subject_cannot_carry_extra_headers() -> None:
    sneaky = facts(service="svc\r\nBcc: attacker@evil.org" + "x" * 300)
    text = subject(sneaky)
    assert "\r" not in text
    assert "\n" not in text
    assert len(text) <= MAX_SUBJECT
    message = build_email(sneaky, sender="dr-agent@example.com", to=("a@example.com",))
    parsed = message_from_string(message.as_string(), policy=policy.default)
    assert parsed["Bcc"] is None


def test_plain_and_html_parts() -> None:
    message = build_email(
        facts(), sender="dr-agent@example.com", to=("a@example.com", "b@example.com")
    )
    assert message["To"] == "a@example.com, b@example.com"
    html_part = message.get_body(("html",))
    assert html_part is not None
    html = html_part.get_content()
    assert "Estimate &lt;b&gt;daily&lt;/b&gt;" in html
    assert "<b>daily</b>" not in html
    assert '<a href="http://localhost:8080/#/schedules/s1/runs/r1">' in html
    text = plain_text(facts())
    assert "Schedule: Estimate <b>daily</b> (Daily 06:00 UTC)" in text
    assert "Run: 27 Sep 2026, 06:00 UTC" in text
    kolkata = facts(run_at=RUN_AT.astimezone(ZoneInfo("Asia/Kolkata")))
    assert "Run: 27 Sep 2026, 11:30 UTC+05:30" in plain_text(kolkata)


def test_failure_email_explains_the_error_code() -> None:
    text = plain_text(
        facts(report=None, error_code="PATH_NOT_ALLOWED", manual=True, owner=None, link=None)
    )
    assert "Result: failed (PATH_NOT_ALLOWED)" in text
    assert "no longer allowed" in text
    assert "(run now)" in text
    assert "Owner: not found in the directory" in text
    assert "Open in the dashboard" not in text
    unknown = plain_text(facts(report=None, error_code="SOMETHING_NEW"))
    assert "could not be completed" in unknown


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Estimate Service", "Estimate-Service"),
        ("<script>alert(1)</script>", "script-alert-1-script"),
        ("   ", "fallback"),
        ("ä" * 5, "fallback"),
    ],
)
def test_safe_identifier(raw: str, expected: str) -> None:
    assert safe_identifier(raw, fallback="fallback") == expected
