"""Application runtime context and message building helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from localmind.config.schema import AppConfig
from localmind.core.session import Session, SessionManager
from localmind.llm.manager import ProviderManager
from localmind.memory.sqlite import SQLiteMemoryStore

if TYPE_CHECKING:
    from localmind.core.agent import Agent


@dataclass(slots=True)
class AppContext:
    config: AppConfig
    provider_manager: ProviderManager
    memory: SQLiteMemoryStore
    sessions: SessionManager
    session: Session | None
    agent: Agent


def build_chat_messages(
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_message}]
