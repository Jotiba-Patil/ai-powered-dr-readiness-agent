"""Tool-call annotations on recovery steps: `Tool:`, `Verify-Tool:`, `Rollback-Tool:`.

Each annotation holds one code span in the form `<server>/<tool> {JSON arguments}`
(the JSON object is optional and defaults to `{}`). A bad annotation never fails
the runbook: it adds a parser warning and is ignored, so the step falls back to
an AI proposal or a manual step at execution time (ADR 0002).
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from dr_agent.core.patterns import CODE_SPAN_RE
from dr_agent.models.runbook import PlannedToolCall

# Step field each annotation label fills, keyed by the normalized label.
ANNOTATION_FIELDS: dict[str, str] = {
    "tool": "tool_call",
    "verify tool": "verify_call",
    "rollback tool": "rollback_call",
}

_LABEL_RE = re.compile(r"^\s*(tool|verify[- ]tool|rollback[- ]tool)\s*:\s*(.*)$", re.I | re.S)
_CALL_RE = re.compile(r"^(?P<server>[^/\s]+)/(?P<tool>\S+?)(?:\s+(?P<args>.*))?$", re.S)


def normalize_label(label: str) -> str | None:
    """`Verify-Tool`, `verify tool` -> `verify tool`; None for any other label."""
    key = re.sub(r"[-\s]+", " ", label.strip().lower())
    return key if key in ANNOTATION_FIELDS else None


def match_annotation(text: str) -> tuple[str, str] | None:
    """(normalized label, call text) when a list item is an annotation, else None."""
    match = _LABEL_RE.match(text)
    if match is None:
        return None
    label = re.sub(r"[-\s]+", " ", match.group(1).lower())  # the regex admits known labels only
    return label, code_or_text(match.group(2))


def code_or_text(text: str) -> str:
    """The first code span's content if there is one, else the text itself."""
    spans = CODE_SPAN_RE.findall(text)
    return spans[0].strip() if spans else text.strip()


def parse_call(text: str) -> PlannedToolCall:
    """Parses `<server>/<tool> {JSON}`. Raises ValueError with a readable reason."""
    match = _CALL_RE.match(text.strip())
    if match is None:
        raise ValueError("expected '<server>/<tool> {JSON arguments}'")
    raw_args = (match.group("args") or "").strip()
    arguments: object = {}
    if raw_args:
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            raise ValueError(f"arguments are not valid JSON ({exc.msg})") from exc
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
    try:
        return PlannedToolCall.model_validate(
            {"server": match.group("server"), "tool": match.group("tool"), "arguments": arguments}
        )
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]) for err in exc.errors())
        raise ValueError(f"invalid {fields}") from exc


def build_calls(
    annotations: list[tuple[str, str]], step_number: int, warnings: list[str]
) -> dict[str, PlannedToolCall]:
    """Step fields (`tool_call`, ...) from (label, call text) pairs; bad ones become warnings."""
    calls: dict[str, PlannedToolCall] = {}
    for label, text in annotations:
        field = ANNOTATION_FIELDS[label]
        name = label.title().replace(" ", "-")
        if field in calls:
            warnings.append(f"step {step_number}: duplicate {name} annotation ignored")
            continue
        try:
            calls[field] = parse_call(text)
        except ValueError as exc:
            warnings.append(f"step {step_number}: {name} annotation ignored: {exc}")
    return calls
