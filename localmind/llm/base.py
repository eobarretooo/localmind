"""Provider interfaces for language models."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderConnectionError(RuntimeError):
    """Raised when a configured model endpoint cannot be reached."""


class LLMProvider(ABC):
    """Abstract provider interface."""

    @abstractmethod
    async def chat(self, messages: list[dict], stream: bool = False) -> str:
        """Return the assistant text for the given chat messages."""
