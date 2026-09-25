"""Shared base model: camelCase JSON (as in the brief), snake_case Python, strict inputs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Accepts and emits camelCase; unknown fields are rejected so bad input fails loudly."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    def to_json_dict(self) -> dict[str, object]:
        """JSON-ready dict using the camelCase field names."""
        return self.model_dump(mode="json", by_alias=True)
