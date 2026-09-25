"""`python -m dr_agent.mock_mcp [--transport stdio|http] [--host H] [--port P] [--scenario FILE]`.

stdio is for local use (the default `mcp-servers.json` launches it this way);
streamable HTTP is for the Docker `mock-mcp` service on an internal network.
The scenario file can also be given with `MOCK_MCP_SCENARIO`.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings

from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.mock_mcp.state import Scenario, load_scenario
from dr_agent.utils.errors import ConfigError


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m dr_agent.mock_mcp")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", default=os.environ.get("MOCK_MCP_SCENARIO"))
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="Host header the HTTP transport accepts, e.g. mock-mcp:* (DNS-rebinding protection)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        scenario = load_scenario(Path(args.scenario)) if args.scenario else Scenario()
    except ConfigError as exc:
        print(exc.to_dict(), file=sys.stderr)
        return 1
    server = build_server(DrEnvironment(scenario))
    if args.transport == "http":
        security = (
            TransportSecuritySettings(allowed_hosts=list(args.allowed_host))
            if args.allowed_host
            else None
        )
        server.run("streamable-http", host=args.host, port=args.port, transport_security=security)
    else:
        server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
