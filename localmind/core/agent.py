"""Minimal agent implementation."""

from __future__ import annotations

import re

from localmind.config.schema import DEFAULT_SYSTEM_PROMPT
from localmind.core.context import build_chat_messages
from localmind.core.session import Session
from localmind.llm.manager import ProviderManager
from localmind.memory.sqlite import MemoryRecord, SQLiteMemoryStore


class Agent:
    """Thin coordinator that builds prompts and calls the selected provider."""

    _IDENTITY_QUESTION_RE = re.compile(
        r"^\s*(?:what\s+are\s+you|who\s+are\s+you|what(?:'s|\s+is)\s+your\s+name)\s*[?.!]*\s*$",
        re.IGNORECASE,
    )
    _USER_INTRODUCTION_RE = re.compile(
        r"^\s*(?:hi|hello|hey)[,!.\s]*my\s+name\s+is\s+(?P<name>[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,2})\s*[.!?]*\s*$",
        re.IGNORECASE,
    )
    _USER_NAME_STATEMENT_RE = re.compile(
        r"(?:^|\b)my\s+name\s+is\s+(?P<name>[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,2})\s*[.!?]*\s*$",
        re.IGNORECASE,
    )
    _USER_NAME_QUESTION_RE = re.compile(r"^\s*what(?:'s|\s+is)\s+my\s+name\s*[?.!]*\s*$", re.IGNORECASE)

    def __init__(
        self,
        system_prompt: str,
        provider_manager: ProviderManager,
        max_history_messages: int = 12,
        memory_store: SQLiteMemoryStore | None = None,
        max_memory_items: int = 5,
    ) -> None:
        self._system_prompt = system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self._provider_manager = provider_manager
        self._max_history_messages = max_history_messages
        self._memory_store = memory_store
        self._max_memory_items = max_memory_items

    async def ask(self, user_message: str, session: Session | None = None) -> str:
        if self._is_identity_question(user_message):
            answer = "I am LocalMind, a local-first AI assistant running on your Linux machine."
            if session is not None:
                session.append("user", user_message)
                session.append("assistant", answer)
            return answer

        introduced_name = self._extract_user_name(user_message)
        if introduced_name is not None:
            answer = f"Nice to meet you, {introduced_name}."
            if session is not None:
                session.append("user", user_message)
                session.append("assistant", answer)
            return answer

        history: list[dict[str, str]] = []
        if session is not None:
            history = session.load_recent_messages(self._max_history_messages)
        relevant_memories = self._find_relevant_memories(user_message)
        messages = build_chat_messages(self._system_prompt, history, user_message, relevant_memories=relevant_memories)

        provider = self._provider_manager.get_provider()
        answer = await provider.chat(messages)
        answer = self._apply_follow_up_name_safeguard(
            user_message=user_message,
            history=history,
            relevant_memories=relevant_memories,
            answer=answer,
        )

        if session is not None:
            session.append("user", user_message)
            session.append("assistant", answer)

        return answer

    @classmethod
    def _is_identity_question(cls, user_message: str) -> bool:
        return bool(cls._IDENTITY_QUESTION_RE.match(user_message))

    @classmethod
    def _extract_user_name(cls, user_message: str) -> str | None:
        match = cls._USER_INTRODUCTION_RE.match(user_message)
        if match is None:
            return None
        return match.group("name")

    @classmethod
    def _extract_stated_user_name(cls, user_message: str) -> str | None:
        match = cls._USER_NAME_STATEMENT_RE.search(user_message)
        if match is None:
            return None
        return match.group("name")

    def _find_relevant_memories(self, user_message: str) -> list[MemoryRecord]:
        if self._memory_store is None:
            return []
        return self._memory_store.find_relevant_memories(user_message, limit=self._max_memory_items)

    @classmethod
    def _apply_follow_up_name_safeguard(
        cls,
        user_message: str,
        history: list[dict[str, str]],
        relevant_memories: list[MemoryRecord],
        answer: str,
    ) -> str:
        if not cls._USER_NAME_QUESTION_RE.match(user_message):
            return answer

        remembered_name = cls._extract_name_from_history(history)
        if remembered_name is None:
            remembered_name = cls._extract_name_from_memories(relevant_memories)
        if remembered_name is None:
            return answer
        return f"Your name is {remembered_name}."

    @classmethod
    def _extract_name_from_history(cls, history: list[dict[str, str]]) -> str | None:
        for message in reversed(history):
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            name = cls._extract_stated_user_name(content)
            if name is not None:
                return name
        return None

    @classmethod
    def _extract_name_from_memories(cls, memories: list[MemoryRecord]) -> str | None:
        for memory in memories:
            name = cls._extract_stated_user_name(memory.content)
            if name is not None:
                return name
        return None
