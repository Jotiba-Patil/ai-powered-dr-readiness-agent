"""Shared CLI plumbing: exit codes, startup (settings and logging), error exits."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Coroutine
from typing import Annotated, NoReturn

import typer

from dr_agent.config import Settings, load_settings
from dr_agent.utils.errors import AppError
from dr_agent.utils.logging import configure_logging

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CRITICAL = 2

VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Emit LOG_LEVEL logs.")]


def startup(verbose: bool) -> Settings:
    try:
        settings = load_settings()
    except AppError as exc:
        fail(exc)
    configure_logging(settings.log_level if verbose else "warning", stream=sys.stderr)
    return settings


def run_or_exit[T](coro: Coroutine[object, object, T]) -> T:
    try:
        return asyncio.run(coro)
    except AppError as exc:
        fail(exc)


def fail(exc: AppError) -> NoReturn:
    typer.echo(json.dumps(exc.to_dict(), default=str), err=True)
    raise typer.Exit(EXIT_ERROR)
