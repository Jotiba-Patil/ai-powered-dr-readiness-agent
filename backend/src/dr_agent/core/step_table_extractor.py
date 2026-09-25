"""Extracts Step entries from a Recovery Steps table (as opposed to a list)."""

from __future__ import annotations

from markdown_it.tree import SyntaxTreeNode
from pydantic import ValidationError

from dr_agent.core.annotations import ANNOTATION_FIELDS, build_calls, code_or_text, normalize_label
from dr_agent.core.patterns import clean_markup
from dr_agent.core.text_lines import inline_text
from dr_agent.core.time_parser import find_minutes
from dr_agent.models.runbook import Step

_DEFAULT_MINUTES = 10


def steps_from_table(table: SyntaxTreeNode, warnings: list[str]) -> list[Step]:
    header, rows = _read_table(table)

    action_idx = _column_index(header, ("action", "step", "description"))
    owner_idx = _column_index(header, ("owner",))
    target_idx = _column_index(header, ("target", "target system"))
    time_idx = _column_index(header, ("estimated minutes", "time", "minutes", "duration"))
    validation_idx = _column_index(header, ("validation", "validation command"))
    tool_columns = _tool_columns(header)

    steps: list[Step] = []
    for row_number, row in enumerate(rows, start=1):
        action_raw = clean_markup(_cell(row, action_idx) or " ".join(row)).strip()
        action = action_raw or "Unspecified action"
        owner = _cell(row, owner_idx).strip()
        if not owner:
            owner = "Unspecified"
            warnings.append(f"step {row_number}: no owner found; defaulting to 'Unspecified'")
        target_system = _cell(row, target_idx).strip() or None

        minutes = _parse_table_minutes(_cell(row, time_idx))
        if minutes is None:
            minutes = _DEFAULT_MINUTES
            warnings.append(
                f"step {row_number}: no time estimate found; "
                f"defaulting to {_DEFAULT_MINUTES} minutes"
            )

        validation_text = _cell(row, validation_idx).strip()
        validation_command = clean_markup(validation_text).strip() or None
        annotations = [
            (label, code_or_text(_cell(row, idx))) for label, idx in tool_columns if _cell(row, idx)
        ]
        calls = build_calls(annotations, row_number, warnings)

        try:
            steps.append(
                Step(
                    step_number=row_number,
                    action=action,
                    owner=owner,
                    target_system=target_system,
                    estimated_minutes=float(minutes),
                    validation_command=validation_command,
                    depends_on=[],
                    **calls,
                )
            )
        except ValidationError:
            warnings.append(f"step {row_number}: skipped, could not build a valid step")
    return steps


def _read_table(table: SyntaxTreeNode) -> tuple[list[str], list[list[str]]]:
    header: list[str] = []
    rows: list[list[str]] = []
    for section in table.children:
        for table_row in section.children:
            cells = [inline_text(cell).strip() for cell in table_row.children]
            if section.type == "thead":
                header = [cell.lower() for cell in cells]
            else:
                rows.append(cells)
    return header, rows


def _column_index(header: list[str], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in header:
            return header.index(key)
    return None


def _tool_columns(header: list[str]) -> list[tuple[str, int]]:
    """(annotation label, column index) for `Tool`, `Verify Tool`, `Rollback Tool` columns."""
    columns: list[tuple[str, int]] = []
    for idx, name in enumerate(header):
        label = normalize_label(name)
        if label in ANNOTATION_FIELDS:
            columns.append((label, idx))
    return columns


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def _parse_table_minutes(cell: str) -> int | None:
    """A minutes-column cell is usually a bare number; fall back to unit parsing."""
    stripped = cell.strip()
    if not stripped:
        return None
    try:
        return round(float(stripped))
    except ValueError:
        minutes, _warning = find_minutes(stripped)
        return minutes
