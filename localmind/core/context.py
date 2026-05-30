"""Application runtime context."""

from __future__ import annotations

from dataclasses import dataclass

from localmind.config.schema import AppConfig
from localmind.core.agent import Agent
from localmind.core.session import Session
from localmind.llm.manager import ProviderManager
from localmind.memory.sqlite import SQLiteMemoryStore


@dataclass(slots=True)
class AppContext:
    config: AppConfig
    provider_manager: ProviderManager
    memory: SQLiteMemoryStore
    session: Session
    agent: Agent
