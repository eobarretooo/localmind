"""Persistent chat sessions backed by SQLite."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from localmind.memory.sqlite import MessageRecord, SQLiteMemoryStore, SessionRecord

_DEFAULT_SESSION_TITLE = "New session"
_WHITESPACE_RE = re.compile(r"\s+")


class SessionNotFoundError(RuntimeError):
    """Raised when a requested session does not exist."""


@dataclass(slots=True)
class Session:
    memory: SQLiteMemoryStore
    record: SessionRecord

    @property
    def session_id(self) -> str:
        return self.record.id

    def append(self, role: str, content: str) -> MessageRecord:
        message = self.memory.add_message(self.session_id, role, content)
        if role == "user" and self.record.title == _DEFAULT_SESSION_TITLE:
            title = generate_session_title(content)
            updated = self.memory.update_session_title(self.session_id, title)
            if updated is not None:
                self.record = updated
        else:
            refreshed = self.memory.get_session(self.session_id)
            if refreshed is not None:
                self.record = refreshed
        return message

    def load_messages(self) -> list[dict[str, str]]:
        return [_message_to_payload(message) for message in self.memory.load_messages(self.session_id)]

    def load_recent_messages(self, limit: int) -> list[dict[str, str]]:
        return [_message_to_payload(message) for message in self.memory.load_recent_messages(self.session_id, limit)]


class SessionManager:
    """Create, load, list, and delete persistent sessions."""

    def __init__(self, memory: SQLiteMemoryStore) -> None:
        self._memory = memory

    def create(self) -> Session:
        record = self._memory.create_session(session_id=str(uuid.uuid4()), title=_DEFAULT_SESSION_TITLE)
        return Session(memory=self._memory, record=record)

    def open(self, session_id: str) -> Session:
        record = self._memory.get_session(session_id)
        if record is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return Session(memory=self._memory, record=record)

    def list(self) -> list[SessionRecord]:
        return self._memory.list_sessions()

    def delete(self, session_id: str) -> None:
        if not self._memory.delete_session(session_id):
            raise SessionNotFoundError(f"Session not found: {session_id}")


def generate_session_title(content: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", content).strip()
    if not normalized:
        return _DEFAULT_SESSION_TITLE
    if len(normalized) <= 60:
        return normalized
    return normalized[:57].rstrip() + "..."


def _message_to_payload(message: MessageRecord) -> dict[str, str]:
    return {"role": message.role, "content": message.content}
