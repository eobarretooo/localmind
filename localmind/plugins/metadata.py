"""Plugin manifest metadata models."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

PLUGIN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_\-]{0,63}$")


class PluginMetadata(BaseModel):
    """Validated metadata loaded from ``plugin.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    description: str
    entrypoint: str
    author: str | None = None
    commands: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not PLUGIN_NAME_PATTERN.fullmatch(cleaned):
            raise ValueError("must match ^[a-z][a-z0-9_\\-]{0,63}$")
        return cleaned

    @field_validator("version", "description", "entrypoint")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("author")
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("commands", "tools")
    @classmethod
    def _validate_string_list(cls, values: list[str]) -> list[str]:
        cleaned_values: list[str] = []
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("list entries must not be blank")
            cleaned_values.append(cleaned)
        return cleaned_values
