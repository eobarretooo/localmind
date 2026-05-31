"""Plugin enabled/disabled state storage."""

from __future__ import annotations

from localmind.memory.sqlite import SQLiteMemoryStore


class PluginStateStore:
    """Persist plugin enabled state in the existing SQLite database."""

    def __init__(self, memory_store: SQLiteMemoryStore) -> None:
        self._memory_store = memory_store

    def get_enabled(self, plugin_name: str) -> bool | None:
        return self._memory_store.get_plugin_enabled(plugin_name)

    def set_enabled(self, plugin_name: str, enabled: bool) -> None:
        self._memory_store.set_plugin_enabled(plugin_name, enabled)
