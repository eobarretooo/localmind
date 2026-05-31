"""SQLite-backed session, message, and local memory storage."""

from __future__ import annotations

import sqlite3
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "you",
    "your",
}


@dataclass(slots=True, frozen=True)
class SessionRecord:
    id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class MessageRecord:
    id: int
    session_id: str
    role: str
    content: str
    created_at: str


@dataclass(slots=True, frozen=True)
class MemoryRecord:
    id: str
    content: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str


class SQLiteMemoryStore:
    """Small SQLite store for sessions and chat messages."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS plugin_states (
                    name TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create_session(self, session_id: str, title: str) -> SessionRecord:
        timestamp = _timestamp_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, timestamp, timestamp),
            )
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(row)

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._session_from_row(row)

    def list_sessions(self) -> list[SessionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC, created_at DESC, id DESC"
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return result.rowcount > 0

    def update_session_title(self, session_id: str, title: str) -> SessionRecord | None:
        timestamp = _timestamp_now()
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, timestamp, session_id),
            )
            if result.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(row)

    def add_message(self, session_id: str, role: str, content: str) -> MessageRecord:
        timestamp = _timestamp_now()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, timestamp),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to persist message.")
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (timestamp, session_id),
            )
            row = connection.execute(
                "SELECT id, session_id, role, content, created_at FROM messages WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._message_from_row(row)

    def load_messages(self, session_id: str) -> list[MessageRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def load_recent_messages(self, session_id: str, limit: int) -> list[MessageRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM (
                    SELECT id, session_id, role, content, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) recent
                ORDER BY id ASC
                """,
                (session_id, limit),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def add_memory(self, content: str, tags: list[str] | tuple[str, ...]) -> MemoryRecord:
        timestamp = _timestamp_now()
        memory_id = str(uuid.uuid4())
        normalized_tags = _normalize_tags(tags)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memories (id, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (memory_id, content, json.dumps(normalized_tags), timestamp, timestamp),
            )
            row = connection.execute(
                "SELECT id, content, tags, created_at, updated_at FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        return self._memory_from_row(row)

    def list_memories(self, limit: int) -> list[MemoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, tags, created_at, updated_at
                FROM memories
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, content, tags, created_at, updated_at FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        if row is None:
            return None
        return self._memory_from_row(row)

    def search_memories(self, query: str, limit: int) -> list[MemoryRecord]:
        search_term = f"%{query.lower()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, tags, created_at, updated_at
                FROM memories
                WHERE lower(content) LIKE ? OR lower(tags) LIKE ?
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT ?
                """,
                (search_term, search_term, limit),
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def find_relevant_memories(self, user_message: str, limit: int) -> list[MemoryRecord]:
        keywords = _extract_keywords(user_message)
        if not keywords:
            return []

        where_clauses: list[str] = []
        parameters: list[str | int] = []
        for keyword in keywords:
            where_clauses.append("lower(content) LIKE ?")
            parameters.append(f"%{keyword}%")
            where_clauses.append("lower(tags) LIKE ?")
            parameters.append(f"%{keyword}%")

        candidate_limit = max(limit * 10, 25)
        parameters.append(candidate_limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, content, tags, created_at, updated_at
                FROM memories
                WHERE {' OR '.join(where_clauses)}
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()

        scored: list[tuple[int, MemoryRecord]] = []
        for row in rows:
            record = self._memory_from_row(row)
            searchable_text = f"{record.content}\n{' '.join(record.tags)}".lower()
            score = sum(1 for keyword in keywords if keyword in searchable_text)
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:limit]]

    def delete_memory(self, memory_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return result.rowcount > 0

    def clear_memories(self) -> int:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM memories")
        return result.rowcount

    def get_plugin_enabled(self, name: str) -> bool | None:
        with self._connect() as connection:
            row = connection.execute("SELECT enabled FROM plugin_states WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return bool(row["enabled"])

    def set_plugin_enabled(self, name: str, enabled: bool) -> None:
        timestamp = _timestamp_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO plugin_states (name, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (name, int(enabled), timestamp, timestamp),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _session_from_row(row: sqlite3.Row | None) -> SessionRecord:
        if row is None:
            raise RuntimeError("Expected session row to exist.")
        return SessionRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _message_from_row(row: sqlite3.Row | None) -> MessageRecord:
        if row is None:
            raise RuntimeError("Expected message row to exist.")
        return MessageRecord(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _memory_from_row(row: sqlite3.Row | None) -> MemoryRecord:
        if row is None:
            raise RuntimeError("Expected memory row to exist.")
        raw_tags = row["tags"]
        parsed_tags = json.loads(str(raw_tags)) if raw_tags else []
        return MemoryRecord(
            id=str(row["id"]),
            content=str(row["content"]),
            tags=tuple(str(tag) for tag in parsed_tags),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def _timestamp_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = tag.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _extract_keywords(text: str) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) < 3 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords
