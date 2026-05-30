"""Simple session boundary backed by SQLite memory."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from localmind.memory.sqlite import SQLiteMemoryStore


@dataclass(slots=True)
class Session:
    memory: SQLiteMemoryStore
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def append(self, role: str, content: str) -> None:
        self.memory.add_message(self.session_id, role, content)

    def load_messages(self) -> list[dict[str, str]]:
        return self.memory.load_messages(self.session_id)
