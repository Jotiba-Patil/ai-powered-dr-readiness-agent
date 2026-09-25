"""PreToolUse hook for Edit/Write: protect secrets, lock files and the original brief.

Also blocks writing obvious hardcoded secrets and `Any` type escapes in Python.
Exit code 2 blocks the call. Fails open on parse errors.
"""
import json
import re
import sys

PROTECTED_NAMES = (".env", "uv.lock", "package-lock.json")
PROTECTED_SUFFIX = ("AI-Powered Disaster.md",)
SECRET_RE = re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.I)
ANY_RE = re.compile(r":\s*Any\b|->\s*Any\b|\bList\[Any\]|\bdict\[str,\s*Any\]")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input", {})
        path = str(tool_input.get("file_path", "")).replace("\\", "/")
        content = str(tool_input.get("content", "") or tool_input.get("new_string", ""))
    except (json.JSONDecodeError, AttributeError):
        return 0

    name = path.rsplit("/", 1)[-1]
    if name in PROTECTED_NAMES or name.startswith(".env") and name != ".env.example":
        print(f"Blocked: {name} is protected (secrets or generated lock file).", file=sys.stderr)
        return 2
    if any(path.endswith(s) for s in PROTECTED_SUFFIX):
        print("Blocked: the original brief is read-only. Edit docs/IMPLEMENTATION_PLAN.md instead.", file=sys.stderr)
        return 2
    if SECRET_RE.search(content):
        print("Blocked: content looks like a hardcoded secret. Use config/env.", file=sys.stderr)
        return 2
    if path.endswith(".py") and "/tests/" not in path and ANY_RE.search(content):
        print("Blocked: `Any` is not allowed in application code (mypy --strict policy). Use a precise type.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
