"""PreToolUse hook for Bash: block destructive or off-policy commands.

Exit code 2 blocks the call and feeds stderr back to Claude.
Fails open (exit 0) on any parsing problem so it never bricks the session.
"""
import json
import re
import sys

BLOCKED = [
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\.\.?|\*)(\s|$)", "recursive delete of a broad path"),
    (r"\bgit\s+push\b.*(--force|-f\b)", "force push"),
    (r"\bgit\s+reset\s+--hard\b", "hard reset"),
    (r"\bgit\s+clean\s+-[a-z]*f", "git clean -f"),
    (r"\b(cat|type|Get-Content)\b.*\.env(\s|$)", "reading .env secrets"),
    (r"\bpip\s+install\b", "use `uv add` / `uv sync` instead of pip"),
    (r"\bcurl\b.*\|\s*(sh|bash)", "piping downloads into a shell"),
    (r"\b(anthropic|openai)\b.*(pip|uv add|npm i)", "proprietary LLM SDK is out of scope (open source only)"),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = payload.get("tool_input", {}).get("command", "")
    except (json.JSONDecodeError, AttributeError):
        return 0
    for pattern, reason in BLOCKED:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"Blocked by project hook: {reason}. Command: {command}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
