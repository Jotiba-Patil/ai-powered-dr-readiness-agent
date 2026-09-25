"""PostToolUse hook for Edit/Write: auto-format, then report lint problems and file size.

Skips silently when tools are not installed yet (early phases).
Exit code 2 surfaces lint output to Claude; formatting itself never fails the call.
"""
import json
import shutil
import subprocess
import sys

MAX_LINES = 200


def run(cmd: list[str]) -> subprocess.CompletedProcess[str] | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        path = str(payload.get("tool_input", {}).get("file_path", ""))
    except (json.JSONDecodeError, AttributeError):
        return 0

    problems: list[str] = []
    norm = path.replace("\\", "/")

    if norm.endswith(".py"):
        run(["ruff", "format", path])
        res = run(["ruff", "check", "--fix", path])
        if res and res.returncode != 0:
            problems.append(res.stdout.strip() or res.stderr.strip())
    elif norm.endswith((".ts", ".tsx", ".css", ".json")) and "/frontend/" in norm:
        run(["npx", "--no-install", "prettier", "--write", path])

    if norm.endswith((".py", ".ts", ".tsx")):
        try:
            with open(path, encoding="utf-8") as fh:
                lines = sum(1 for _ in fh)
            if lines > MAX_LINES:
                problems.append(f"{path} has {lines} lines (limit {MAX_LINES}). Split by responsibility.")
        except OSError:
            pass

    if problems:
        print("\n".join(p for p in problems if p), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
