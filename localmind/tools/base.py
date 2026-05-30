"""Base classes for future tool definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, input_text: str) -> str:
        """Execute the tool synchronously."""
