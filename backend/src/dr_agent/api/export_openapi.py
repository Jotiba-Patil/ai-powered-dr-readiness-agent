"""Write the API's OpenAPI schema to a file for the frontend's generated client.

`uv run poe gen-api` runs this and then `openapi-typescript` in `frontend/`.
`tests/unit/test_openapi_export.py` fails when the committed
`frontend/openapi.json` no longer matches the app, so the client cannot drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dr_agent.api.app import create_app
from dr_agent.config import Settings


def build_openapi_json() -> str:
    """The schema as stable, pretty-printed JSON (independent of `.env` and the environment)."""
    app = create_app(Settings(_env_file=None, llm_provider="none"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m dr_agent.api.export_openapi OUTPUT.json", file=sys.stderr)
        return 1
    Path(argv[0]).write_text(build_openapi_json(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
