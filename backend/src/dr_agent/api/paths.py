"""Allow-listed server-side file access for `GET /api/v1/dr/analyze`.

A requested path is resolved (following `..` and symlinks) against the
allow-listed directory and rejected unless the result still lies inside it and
has an expected extension. Absolute paths and drive letters resolve outside
the base and are rejected the same way. Error messages echo only the path the
client sent, never the resolved server path.
"""

from __future__ import annotations

from pathlib import Path

from dr_agent.utils.errors import NotFoundError, PathNotAllowedError


def resolve_allowed_path(base_dir: Path, requested: str, *, suffixes: tuple[str, ...]) -> Path:
    base = base_dir.resolve()
    # Checked explicitly: from Python 3.13, resolving a path with a NUL byte no longer
    # raises on every platform, so the file-system error cannot be relied on.
    if "\x00" in requested:
        raise PathNotAllowedError(f"invalid path: {requested!r}")
    try:
        candidate = (base / requested).resolve()
    except (OSError, ValueError) as exc:
        raise PathNotAllowedError(f"invalid path: {requested!r}") from exc
    if not candidate.is_relative_to(base):
        raise PathNotAllowedError(
            f"path {requested!r} is outside the allowed directory",
            details={"hint": "use a path relative to API_ALLOWED_DIR, e.g. runbooks/x.md"},
        )
    if candidate.suffix.lower() not in suffixes:
        raise PathNotAllowedError(f"path {requested!r} must end with one of {', '.join(suffixes)}")
    if not candidate.is_file():
        raise NotFoundError(f"file not found: {requested!r}")
    return candidate
