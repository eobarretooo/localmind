"""Application runtime context and message building helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from localmind.config.schema import AppConfig
from localmind.core.session import Session, SessionManager
from localmind.llm.manager import ProviderManager
from localmind.memory.sqlite import MemoryRecord, SQLiteMemoryStore

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
    relevant_memories: list[MemoryRecord] | None = None,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system_prompt}]
    memory_message = build_memory_context_message(relevant_memories or [])
    if memory_message is not None:
        messages.append({"role": "system", "content": memory_message})
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def build_memory_context_message(relevant_memories: list[MemoryRecord]) -> str | None:
    if not relevant_memories:
        return None

    lines = ["Relevant local memories:"]
    for memory in relevant_memories:
        line = f"- {memory.content.strip()}"
        if memory.tags:
            line += f" [tags: {', '.join(memory.tags)}]"
        lines.append(line)
    return "\n".join(lines)
