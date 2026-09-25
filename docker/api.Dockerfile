# syntax=docker/dockerfile:1
# DR Readiness Agent API. Build context: repository root (see docker-compose.yml).

# ---- build: resolve the locked dependencies into a venv, then install the project ----
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first so this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY backend/src backend/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---- runtime: venv + sample data only, non-root, no build tools ----
FROM python:3.12-slim-bookworm AS runtime
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app     && mkdir /data && chown app /data
# /data holds dr-agent.db (analyses and executions) on the dr-agent-data volume
# (a new volume copies this ownership).
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
# Samples for the dashboard picker and GET /api/v1/dr/analyze (the only readable directory).
COPY mock-data ./mock-data
# Runbook execution (off unless EXECUTION_ENABLED=true): the allow-list and the MCP servers
# (the bundled mock server as the compose service `mock-mcp`).
COPY execution-policy.json ./config/execution-policy.json
COPY docker/mcp-servers.json ./config/mcp-servers.json
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    PORT=8000 \
    API_ALLOWED_DIR=/app/mock-data     DB_PATH=/data/dr-agent.db     EXECUTION_POLICY_FILE=/app/config/execution-policy.json     MCP_SERVERS_FILE=/app/config/mcp-servers.json
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]
CMD ["python", "-m", "dr_agent.api"]
