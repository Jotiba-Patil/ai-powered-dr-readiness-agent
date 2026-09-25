"""DRReadinessReport -> a simple, self-contained HTML report.

Autoescaping is mandatory here, not optional: runbook text is untrusted and
several report fields (owner, gap descriptions, the LLM summary) can carry it
through verbatim, so this is the one place in the app that renders it as markup.
"""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

from dr_agent.models.report import DRReadinessReport

_env = Environment(
    loader=PackageLoader("dr_agent", "templates"),
    autoescape=select_autoescape(enabled_extensions=("jinja",), default_for_string=True),
)
_template = _env.get_template("report.html.jinja")


def format_html(report: DRReadinessReport) -> str:
    return _template.render(report=report)
