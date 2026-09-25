"""`python -m dr_agent.api` (and `uv run poe dev-api`): serve the API with Uvicorn.

Uvicorn handles SIGINT/SIGTERM; the app lifespan then cancels unfinished jobs.
"""

from __future__ import annotations

import json
import sys

import uvicorn

from dr_agent.api.app import create_app
from dr_agent.config import load_settings
from dr_agent.utils.errors import ConfigError
from dr_agent.utils.logging import configure_logging


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(json.dumps(exc.to_dict(), default=str), file=sys.stderr)
        return 1
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.port,
        log_level=settings.log_level,
        timeout_graceful_shutdown=10,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
