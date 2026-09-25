"""FastAPI application factory.

`create_app()` takes validated settings plus optional injected providers
(tests pass a `FakeProvider` and a seeded, no-sleep `MockHealthChecker`);
anything not injected is built from settings in `wiring.py`. The lifespan owns
the shared `httpx.AsyncClient` and the job store, and on shutdown cancels
unfinished analysis jobs before closing the client (graceful shutdown). With
`EXECUTION_ENABLED=true` it also opens the execution runtime (MCP connections,
store, restart recovery) and stops it again in the same task, as anyio requires.
With `HISTORY_ENABLED=true` (default) every finished analysis is stored (ADR 0007),
and with `KNOWLEDGE_ENABLED=true` new analyses use that history (ADR 0009).
"""

from __future__ import annotations

import random
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dr_agent import __version__
from dr_agent.api.analysis_lookup import history_saver
from dr_agent.api.deps import AppState
from dr_agent.api.errors import install_error_handlers
from dr_agent.api.execution_service import DEFAULT_TICK_SECONDS, ExecutionService
from dr_agent.api.jobs import JobStore
from dr_agent.api.middleware import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    request_context_middleware,
    security_headers_middleware,
)
from dr_agent.api.openapi import openapi_builder
from dr_agent.api.routes import router
from dr_agent.api.routes_execution import router as execution_router
from dr_agent.api.routes_history import router as history_router
from dr_agent.api.routes_samples import router as samples_router
from dr_agent.api.routes_steps import router as steps_router
from dr_agent.config import Settings
from dr_agent.execution_runtime import open_execution_runtime
from dr_agent.health.base import HealthChecker
from dr_agent.history.service import open_history, provenance
from dr_agent.knowledge.service import open_knowledge
from dr_agent.llm.base import LLMProvider
from dr_agent.tools.mcp_convert import ClientFactory
from dr_agent.utils.logging import get_logger
from dr_agent.wiring import build_checker, build_llm

_log = get_logger("dr_agent.api")


def create_app(
    settings: Settings,
    *,
    llm: LLMProvider | None = None,
    checker: HealthChecker | None = None,
    rng: random.Random | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    mcp_factories: Mapping[str, ClientFactory] | None = None,
    execution_tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        chosen_rng = rng or random.Random()  # noqa: S311 -- latency/jitter only, not security
        async with httpx.AsyncClient() as client, AsyncExitStack() as stack:
            chosen_llm = llm or build_llm(settings, client, chosen_rng)
            execution: ExecutionService | None = None
            if settings.execution_enabled:
                runtime = await stack.enter_async_context(
                    open_execution_runtime(
                        settings, chosen_llm, rng=chosen_rng, factories=mcp_factories
                    )
                )
                execution = ExecutionService(runtime, tick_seconds=execution_tick_seconds)
                execution.start_ticker()
                stack.push_async_callback(execution.shutdown)
            history = await open_history(settings)
            jobs = JobStore(
                max_concurrent=settings.api_max_concurrent_jobs,
                max_stored=settings.api_max_stored_jobs,
                on_success=history_saver(history, provenance(settings)) if history else None,
            )
            app.state.dr = AppState(
                settings=settings,
                llm=chosen_llm,
                checker=checker or build_checker(settings, client, chosen_rng),
                jobs=jobs,
                started_at=monotonic(),
                monotonic=monotonic,
                execution=execution,
                history=history,
                knowledge=open_knowledge(settings) if history else None,
            )
            _log.info(
                "api_started",
                version=__version__,
                llm_provider=settings.llm_provider,
                execution_enabled=execution is not None,
                history_enabled=history is not None,
            )
            try:
                yield
            finally:
                await jobs.shutdown()
                _log.info("api_stopped")

    app = FastAPI(
        title="DR Readiness Agent API",
        version=__version__,
        description="Parse DR runbooks, check dependency health and produce readiness reports.",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.middleware("http")(security_headers_middleware)
    app.middleware("http")(request_context_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER, CORRELATION_ID_HEADER],
        expose_headers=["Location", REQUEST_ID_HEADER, CORRELATION_ID_HEADER],
    )
    app.include_router(router)
    app.include_router(samples_router)
    app.include_router(execution_router)
    app.include_router(steps_router)
    app.include_router(history_router)
    app.openapi = openapi_builder(app)  # type: ignore[method-assign]  # documented FastAPI hook
    return app
