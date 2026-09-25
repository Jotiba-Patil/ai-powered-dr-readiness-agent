"""OpenAPI additions for the hand-read `POST /api/v1/dr/analyze` body.

The route reads JSON or multipart itself (see `api/body.py`), so FastAPI cannot
infer its request body. This documents both content types and registers the
JSON model (and the models it references) under `components.schemas`, so the
Phase 6 typed client can be generated from `/openapi.json`.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from dr_agent.api.schemas import AnalyzeJsonRequest

_REF_TEMPLATE = "#/components/schemas/{model}"

ANALYZE_REQUEST_BODY: dict[str, object] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": _REF_TEMPLATE.format(model="AnalyzeJsonRequest")}
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["runbook"],
                    "properties": {
                        "runbook": {"type": "string", "format": "binary"},
                        "inventory": {"type": "string", "format": "binary"},
                    },
                }
            },
        },
    }
}


def openapi_builder(app: FastAPI) -> Callable[[], dict[str, object]]:
    def build() -> dict[str, object]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, description=app.description, routes=app.routes
            )
            components = schema.setdefault("components", {})
            schemas = components.setdefault("schemas", {})
            request_schema = AnalyzeJsonRequest.model_json_schema(
                by_alias=True, ref_template=_REF_TEMPLATE
            )
            for name, definition in request_schema.pop("$defs", {}).items():
                schemas.setdefault(name, definition)
            schemas["AnalyzeJsonRequest"] = request_schema
            app.openapi_schema = schema
        return app.openapi_schema

    return build
