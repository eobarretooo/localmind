"""Minimal agent implementation."""

from __future__ import annotations

import re

from localmind.config.schema import DEFAULT_SYSTEM_PROMPT
from localmind.core.session import Session
from localmind.llm.manager import ProviderManager


class Agent:
    """Thin coordinator that builds prompts and calls the selected provider."""

    _IDENTITY_QUESTION_RE = re.compile(
        r"^\s*(?:what\s+are\s+you|who\s+are\s+you|what(?:'s|\s+is)\s+your\s+name)\s*[?.!]*\s*$",
        re.IGNORECASE,
    )

    def __init__(self, system_prompt: str, provider_manager: ProviderManager) -> None:
        self._system_prompt = system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self._provider_manager = provider_manager

    async def ask(self, user_message: str, session: Session | None = None) -> str:
        if self._is_identity_question(user_message):
            answer = "I am LocalMind, a local-first AI assistant running on your Linux machine."
            if session is not None:
                session.append("user", user_message)
                session.append("assistant", answer)
            return answer

        messages = [{"role": "system", "content": self._system_prompt}]
        if session is not None:
            history = session.load_messages()
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        provider = self._provider_manager.get_provider()
        answer = await provider.chat(messages)

        if session is not None:
            session.append("user", user_message)
            session.append("assistant", answer)

        return answer

    @classmethod
    def _is_identity_question(cls, user_message: str) -> bool:
        return bool(cls._IDENTITY_QUESTION_RE.match(user_message))
