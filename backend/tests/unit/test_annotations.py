"""Tool-call annotations: the `server/tool {JSON}` format, list items and table columns."""

from pathlib import Path

import pytest
from markdown_it.tree import SyntaxTreeNode

from dr_agent.core.annotations import build_calls, match_annotation, normalize_label, parse_call
from dr_agent.core.parser import parse_runbook
from dr_agent.core.sections import parse_tree, split_sections
from dr_agent.core.step_extractor import extract_steps
from dr_agent.models.runbook import PlannedToolCall

REPO_ROOT = Path(__file__).resolve().parents[3]


def _step_nodes(markdown: str) -> list[SyntaxTreeNode]:
    return split_sections(parse_tree(markdown)).sections.get("recovery steps", [])


def test_parse_call_with_arguments() -> None:
    call = parse_call('drsim/k8s.rollout_restart {"deployment": "api", "replicas": 3}')
    assert call == PlannedToolCall(
        server="drsim", tool="k8s.rollout_restart", arguments={"deployment": "api", "replicas": 3}
    )


def test_parse_call_without_arguments_defaults_to_empty_object() -> None:
    assert parse_call("drsim/smoke_run").arguments == {}


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("smoke_run {}", "expected '<server>/<tool>"),
        ("drsim/smoke_run {not json}", "not valid JSON"),
        ("drsim/smoke_run [1, 2]", "must be a JSON object"),
        ("dr sim/x {}", "expected '<server>/<tool>"),
        ("drsim/bad$tool {}", "invalid tool"),
        ("", "expected"),
    ],
)
def test_parse_call_rejects_bad_input(text: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason.replace("$", r"\$").replace("[", r"\[")):
        parse_call(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tool: `a/b {}`", ("tool", "a/b {}")),
        ("verify-tool: `a/b`", ("verify tool", "a/b")),
        ("Rollback Tool:  a/c ", ("rollback tool", "a/c")),
        ("Verify the database `select 1`", None),
        ("Tooling: `a/b`", None),
    ],
)
def test_match_annotation(text: str, expected: tuple[str, str] | None) -> None:
    assert match_annotation(text) == expected


@pytest.mark.parametrize(
    ("header", "label"),
    [("tool", "tool"), ("Verify Tool", "verify tool"), ("rollback-tool", "rollback tool")],
)
def test_normalize_label(header: str, label: str) -> None:
    assert normalize_label(header) == label


def test_normalize_label_rejects_other_columns() -> None:
    assert normalize_label("toolbox") is None


def test_build_calls_warns_on_duplicates_and_bad_annotations() -> None:
    warnings: list[str] = []
    calls = build_calls(
        [("tool", "a/b {}"), ("tool", "a/c {}"), ("verify tool", "nope")], 4, warnings
    )
    assert set(calls) == {"tool_call"}
    assert calls["tool_call"].tool == "b"
    assert warnings == [
        "step 4: duplicate Tool annotation ignored",
        "step 4: Verify-Tool annotation ignored: expected '<server>/<tool> {JSON arguments}'",
    ]


def test_list_annotations_are_read_and_kept_out_of_validation_commands() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "1. Restart the api. Owner: Ann. 5 min.\n"
        '   - Tool: `drsim/k8s_rollout_restart {"deployment": "api"}`\n'
        '   - Verify-Tool: `drsim/k8s_rollout_status {"deployment": "api"}`\n'
        "   - Rollback-Tool: `drsim/k8s_rollout_undo`\n"
        "   - Verify with `curl -f /health`\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert warnings == []
    step = steps[0]
    assert step.validation_command == "curl -f /health"
    assert step.tool_call is not None
    assert step.tool_call.arguments == {"deployment": "api"}
    assert step.verify_call is not None
    assert step.verify_call.tool == "k8s_rollout_status"
    assert step.rollback_call is not None
    assert step.rollback_call.arguments == {}


def test_bad_list_annotation_is_a_warning_not_a_failure() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "1. Restart the api. Owner: Ann. 5 min.\n"
        "   - Tool: `drsim/restart {oops`\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].tool_call is None
    assert steps[0].validation_command is None
    assert len(warnings) == 1
    assert warnings[0].startswith("step 1: Tool annotation ignored: arguments are not valid JSON")


def test_table_tool_columns() -> None:
    markdown = (
        "# Svc\n\n## Recovery Steps\n\n"
        "| Step | Action | Owner | Minutes | Tool | Verify Tool | Rollback Tool |\n"
        "|---|---|---|---|---|---|---|\n"
        '| 1 | Restart | Ann | 5 | `drsim/k8s_rollout_restart {"deployment": "api"}` '
        "| `drsim/k8s_rollout_status` | |\n"
        "| 2 | Promote | Ann | 5 | drsim/db_promote_replica {bad | | |\n"
    )
    steps, warnings = extract_steps(_step_nodes(markdown))
    assert steps[0].tool_call is not None
    assert steps[0].tool_call.tool == "k8s_rollout_restart"
    assert steps[0].verify_call is not None
    assert steps[0].verify_call.arguments == {}
    assert steps[0].rollback_call is None
    assert steps[0].validation_command is None
    assert steps[1].tool_call is None
    assert any(w.startswith("step 2: Tool annotation ignored") for w in warnings)


def test_executable_sample_has_every_step_annotated() -> None:
    path = REPO_ROOT / "mock-data" / "runbooks" / "estimate-service-executable.md"
    runbook = parse_runbook(path.read_text(encoding="utf-8"))
    assert runbook.parser_warnings == []
    assert all(step.tool_call is not None for step in runbook.steps)
    assert all(step.validation_command for step in runbook.steps)
    assert [s.step_number for s in runbook.steps if s.rollback_call] == [2, 5]
    assert all(s.tool_call and s.tool_call.server == "drsim" for s in runbook.steps)


def test_existing_samples_carry_no_annotations() -> None:
    for name in ("estimate-service.md", "payment-gateway.md", "auth-service.md"):
        text = (REPO_ROOT / "mock-data" / "runbooks" / name).read_text(encoding="utf-8")
        runbook = parse_runbook(text)
        assert all(s.tool_call is s.verify_call is s.rollback_call is None for s in runbook.steps)
