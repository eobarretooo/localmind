"""Typed configuration schema."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_SYSTEM_PROMPT = (
    "You are LocalMind, a local-first AI assistant running on the user's Linux machine. "
    "You are the LocalMind assistant, not the raw model backend. The model backend may be "
    "MiniCPM or another local LLM, but you should identify yourself as LocalMind. Answer "
    "directly, clearly, and concisely. Do not repeat the user's request unless necessary."
)


class LoggingConfig(BaseModel):
    level: str = "WARNING"


class AppSettings(BaseModel):
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


class ProviderConfig(BaseModel):
    type: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = "http://127.0.0.1:8080/v1"
    api_key: str | None = None
    model: str = "openbmb/MiniCPM5-1B-GGUF:Q4_K_M"
    timeout_seconds: float = 30.0


class MemoryConfig(BaseModel):
    db_path: Path = Field(default_factory=lambda: Path("~/.local/share/localmind/memory.sqlite3").expanduser())

    @field_validator("db_path", mode="before")
    @classmethod
    def _expand_db_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
