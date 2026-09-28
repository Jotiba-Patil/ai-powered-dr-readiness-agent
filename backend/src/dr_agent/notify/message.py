"""`EmailFacts` -> an email with a plain-text and an autoescaped HTML part.

`EmailMessage` rejects CR/LF in header values; the subject is also stripped of
control characters and shortened, so nothing can add headers through it.
"""

from __future__ import annotations

import re
from email.message import EmailMessage

from jinja2 import Environment, PackageLoader, select_autoescape

from dr_agent.notify.facts import EmailFacts, ReportFacts
from dr_agent.utils.timefmt import display_time

MAX_SUBJECT = 150
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_env = Environment(
    loader=PackageLoader("dr_agent", "templates"),
    autoescape=select_autoescape(enabled_extensions=("jinja",), default_for_string=True),
)
_template = _env.get_template("scheduled_run_email.html.jinja")


def build_email(facts: EmailFacts, *, sender: str, to: tuple[str, ...]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject(facts)
    message["From"] = sender
    message["To"] = ", ".join(to)
    message.set_content(plain_text(facts))
    message.add_alternative(_template.render(facts=facts, lines=_lines(facts)), subtype="html")
    return message


def subject(facts: EmailFacts) -> str:
    if facts.report is None:
        text = f"[DR readiness] {facts.service}: scheduled analysis failed"
    else:
        rto = "" if facts.report.rto_feasible else ", RTO at risk"
        level = facts.report.risk_level.value
        text = f"[DR readiness] {facts.service}: {level} risk ({facts.report.risk_score}/100){rto}"
    return _CONTROL.sub(" ", text)[:MAX_SUBJECT]


def plain_text(facts: EmailFacts) -> str:
    return "\n".join(f"{label}: {value}" if label else value for label, value in _lines(facts))


def _lines(facts: EmailFacts) -> list[tuple[str, str]]:
    lines = [
        ("Schedule", f"{facts.schedule_name} ({facts.cadence})"),
        (
            "Run",
            display_time(facts.run_at, facts.run_at.tzinfo)
            + (" (run now)" if facts.manual else ""),
        ),
        ("Service", facts.service),
        ("Owner", facts.owner or "not found in the directory"),
    ]
    if facts.report is None:
        lines.append(("Result", f"failed ({facts.error_code or 'UNKNOWN'})"))
        lines.append(("Reason", facts.error_text))
    else:
        lines.extend(_report_lines(facts.report))
    lines.extend(("Note", note) for note in facts.notes)
    if facts.link:
        lines.append(("Open in the dashboard", facts.link))
    lines.append(("", "Details, gaps and the execution plan are in the report."))
    return lines


def _report_lines(report: ReportFacts) -> list[tuple[str, str]]:
    feasible = "feasible" if report.rto_feasible else "NOT feasible"
    gaps = ", ".join(f"{count} {severity.value.lower()}" for severity, count in report.gaps.items())
    deps = ", ".join(
        f"{count} {status.value.lower().replace('_', ' ')}"
        for status, count in report.dependencies.items()
        if count
    )
    return [
        ("Risk", f"{report.risk_level.value} ({report.risk_score}/100)"),
        (
            "RTO",
            f"{feasible}: estimated {report.estimated_minutes:g} min of "
            f"{report.stated_rto_minutes:g} min (buffer {report.buffer_minutes:g} min)",
        ),
        ("Gaps", gaps),
        ("Single points of failure", str(report.single_points_of_failure)),
        ("Dependencies", deps or "none declared"),
        (
            "AI analysis",
            "available" if report.ai_analysis_available else "unavailable (rules only)",
        ),
    ]
