"""SQLite-backed session and message storage."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


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


def _timestamp_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
