"""Application lifecycle boundary."""

from __future__ import annotations

from localmind.core.context import AppContext


class ApplicationLifecycle:
    """Owns startup and shutdown for the current runtime."""

    def __init__(self, context: AppContext) -> None:
        self.context = context

    async def __aenter__(self) -> AppContext:
        self.context.memory.initialize()
        return self.context

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
