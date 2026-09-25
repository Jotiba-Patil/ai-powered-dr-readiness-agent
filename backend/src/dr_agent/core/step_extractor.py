"""Extracts Step entries from the runbook's Recovery Steps section."""

from __future__ import annotations

import re

from markdown_it.tree import SyntaxTreeNode
from pydantic import ValidationError

from dr_agent.core.annotations import build_calls, match_annotation
from dr_agent.core.patterns import (
    AFTER_STEP_RE,
    CODE_SPAN_RE,
    HANDLE_RE,
    OWNER_RE,
    PAREN_OWNER_RE,
    STEP_NUMBER_PREFIX_RE,
    TARGET_RE,
    VALIDATION_HINT_RE,
    clean_markup,
)
from dr_agent.core.step_table_extractor import steps_from_table
from dr_agent.core.text_lines import inline_text
from dr_agent.core.time_parser import find_minutes
from dr_agent.models.runbook import Step

_DEFAULT_MINUTES = 10
_ACTION_SPLIT_RE = re.compile(r"\bowner\b|@|\btarget\b", re.IGNORECASE)


def extract_steps(nodes: list[SyntaxTreeNode]) -> tuple[list[Step], list[str]]:
    warnings: list[str] = []
    steps: list[Step] = []
    for node in nodes:
        if node.type == "table":
            steps.extend(steps_from_table(node, warnings))
        elif node.type in ("bullet_list", "ordered_list"):
            steps.extend(_from_list(node, warnings))
    if not steps:
        warnings.append("no recovery steps found")
    return steps, warnings


def _from_list(list_node: SyntaxTreeNode, warnings: list[str]) -> list[Step]:
    steps: list[Step] = []
    for index, item in enumerate(list_node.children, start=1):
        text = " ".join(inline_text(child) for child in item.children if child.type == "paragraph")
        nested_code, annotations = _nested_items(item)
        step = _build_step(index, text, nested_code, annotations, warnings)
        if step is not None:
            steps.append(step)
    return steps


def _nested_items(item: SyntaxTreeNode) -> tuple[list[str], list[tuple[str, str]]]:
    """Validation commands and tool-call annotations nested under a step.

    Annotation items (`Tool:`, `Verify-Tool:`, `Rollback-Tool:`) are never read
    as validation commands, although "verify" would otherwise mark them as one.
    """
    codes: list[str] = []
    annotations: list[tuple[str, str]] = []
    for child in item.children:
        if child.type in ("fence", "code_block"):
            codes.append(child.content.strip())
        if child.type in ("bullet_list", "ordered_list"):
            for sub_item in child.children:
                sub_text = " ".join(
                    inline_text(sub) for sub in sub_item.children if sub.type == "paragraph"
                )
                annotation = match_annotation(sub_text)
                if annotation is not None:
                    annotations.append(annotation)
                elif VALIDATION_HINT_RE.search(sub_text):
                    codes.extend(CODE_SPAN_RE.findall(sub_text))
    return codes, annotations


def _build_step(
    number: int,
    text: str,
    nested_code: list[str],
    annotations: list[tuple[str, str]],
    warnings: list[str],
) -> Step | None:
    prefix_match = STEP_NUMBER_PREFIX_RE.match(clean_markup(text))
    step_number = int(prefix_match.group(1)) if prefix_match else number
    cleaned = clean_markup(STEP_NUMBER_PREFIX_RE.sub("", text, count=1)).strip()

    owner = _find_owner(cleaned, text, step_number, warnings)

    minutes, time_warning = find_minutes(cleaned)
    if minutes is None:
        minutes = _DEFAULT_MINUTES
        warnings.append(
            f"step {step_number}: no time estimate found; defaulting to {_DEFAULT_MINUTES} minutes"
        )
    elif time_warning:
        warnings.append(f"step {step_number}: {time_warning}")

    target_match = TARGET_RE.search(cleaned)
    target_system = target_match.group(1).strip() if target_match else None

    code_in_text = CODE_SPAN_RE.findall(text)
    if code_in_text:
        validation_command = code_in_text[0]
    else:
        validation_command = nested_code[0] if nested_code else None

    depends_on: list[int] = []
    after_match = AFTER_STEP_RE.search(cleaned)
    action_source = cleaned
    if after_match:
        depends_on = sorted({int(n) for n in re.findall(r"\d+", after_match.group(1))})
        stripped = cleaned[: after_match.start()] + cleaned[after_match.end() :]
        action_source = re.sub(r"\(\s*\)", "", stripped).strip()

    action_head = _ACTION_SPLIT_RE.split(action_source, maxsplit=1)[0].strip().rstrip(".,;")
    action = action_head or "Unspecified action"
    calls = build_calls(annotations, step_number, warnings)

    try:
        return Step(
            step_number=step_number,
            action=action,
            owner=owner,
            target_system=target_system,
            estimated_minutes=float(minutes),
            validation_command=validation_command,
            depends_on=depends_on,
            **calls,
        )
    except ValidationError:
        warnings.append(f"step {step_number}: skipped, could not build a valid step")
        return None


def _find_owner(cleaned: str, raw_text: str, step_number: int, warnings: list[str]) -> str:
    owner_match = OWNER_RE.search(cleaned)
    if owner_match:
        return re.split(r"[.,;]", owner_match.group(1).strip(), maxsplit=1)[0].strip()
    handle_match = HANDLE_RE.search(raw_text)
    if handle_match:
        return f"@{handle_match.group(1)}"
    paren_match = PAREN_OWNER_RE.search(raw_text)
    if paren_match:
        return paren_match.group(1).strip()
    warnings.append(f"step {step_number}: no owner found; defaulting to 'Unspecified'")
    return "Unspecified"
