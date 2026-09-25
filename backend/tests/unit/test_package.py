import importlib

import pytest

import dr_agent

FRAMEWORKS = ("fastapi", "typer", "rich", "starlette", "uvicorn")


def test_version_is_semver_like() -> None:
    assert dr_agent.__version__.count(".") == 2


@pytest.mark.parametrize(
    "package",
    ["dr_agent.core", "dr_agent.health", "dr_agent.models", "dr_agent.execution", "dr_agent.tools"],
)
def test_framework_free_packages_import_cleanly(package: str) -> None:
    """core/ and health/ must not depend on web or CLI frameworks (checked by source scan)."""
    module = importlib.import_module(package)
    assert module.__file__ is not None
    from pathlib import Path

    for source in Path(module.__file__).parent.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for framework in FRAMEWORKS:
            assert f"import {framework}" not in text, f"{source} imports {framework}"
            assert f"from {framework}" not in text, f"{source} imports {framework}"


@pytest.mark.parametrize("module", ["dr_agent.service", "dr_agent.loaders", "dr_agent.wiring"])
def test_shared_service_modules_are_framework_free(module: str) -> None:
    """The one pipeline both the CLI and the API call must not depend on either."""
    from pathlib import Path

    source = importlib.import_module(module).__file__
    assert source is not None
    text = Path(source).read_text(encoding="utf-8")
    for framework in FRAMEWORKS:
        assert f"import {framework}" not in text, f"{module} imports {framework}"
        assert f"from {framework}" not in text, f"{module} imports {framework}"


def test_only_the_mcp_modules_import_the_mcp_sdk() -> None:
    """ADR 0001: the SDK stays behind `ToolExecutor`; execution/ never sees it."""
    from pathlib import Path

    package = Path(dr_agent.__file__).parent
    allowed = {"tools/mcp_executor.py", "tools/mcp_convert.py"}
    for source in package.rglob("*.py"):
        relative = source.relative_to(package).as_posix()
        text = source.read_text(encoding="utf-8")
        if relative in allowed or relative.startswith("mock_mcp/"):
            continue
        assert "import mcp" not in text, relative
        assert "from mcp" not in text, relative
