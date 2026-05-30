"""Tiny SQLite-backed message store."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteMemoryStore:
    """Very small SQLite message store for session history."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )

    def load_messages(self, session_id: str) -> list[dict[str, str]]:
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in rows]
