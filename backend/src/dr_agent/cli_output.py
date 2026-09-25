"""CLI output helpers: report format selection and writing to stdout or a file."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console

from dr_agent.formatters.format_html import format_html
from dr_agent.formatters.format_json import format_json
from dr_agent.formatters.format_terminal import render_terminal
from dr_agent.models.report import DRReadinessReport
from dr_agent.utils.errors import AppError


class ReportFormat(StrEnum):
    JSON = "json"
    TERMINAL = "terminal"
    HTML = "html"


class HealthFormat(StrEnum):
    JSON = "json"
    TERMINAL = "terminal"


def render_report(report: DRReadinessReport, fmt: ReportFormat, *, to_file: bool) -> str | None:
    """Return the rendered text, or print straight to a color stdout `Console` (returns None)."""
    if fmt is ReportFormat.JSON:
        return format_json(report)
    if fmt is ReportFormat.HTML:
        return format_html(report)
    if to_file:
        return render_terminal(report)
    render_terminal(report, console=Console())
    return None


def write_output(text: str | None, output: Path | None) -> None:
    if text is None:
        return
    if output is None:
        typer.echo(text)
        return
    try:
        output.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise AppError(f"could not write {output}", details={"reason": str(exc)}) from exc
    typer.echo(f"Report written to {output}", err=True)
