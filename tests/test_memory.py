import asyncio
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from localmind.app import cli
from localmind.config.schema import AppConfig, DEFAULT_SYSTEM_PROMPT
from localmind.core.agent import Agent
from localmind.core.context import build_chat_messages
from localmind.memory.sqlite import SQLiteMemoryStore


class _RecordingProvider:
    def __init__(self, answer: str = "provider answer") -> None:
        self.answer = answer
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.answer


class _RecordingProviderManager:
    def __init__(self, provider: _RecordingProvider) -> None:
        self._provider = provider

    def get_provider(self) -> _RecordingProvider:
        return self._provider


def _build_store(tmp_path: Path) -> SQLiteMemoryStore:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    return store


def _config_for(tmp_path: Path) -> AppConfig:
    return AppConfig.model_validate({"memory": {"db_path": str(tmp_path / "memory.sqlite3")}})


def test_adding_memory_persists_content_and_tags(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    record = store.add_memory("My name is Antonio", tags=["profile", "profile", "User "])

    loaded = store.get_memory(record.id)
    assert loaded is not None
    assert loaded.content == "My name is Antonio"
    assert loaded.tags == ("profile", "user")


def test_listing_memories_returns_saved_records(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    first = store.add_memory("first memory", tags=[])
    second = store.add_memory("second memory", tags=["notes"])

    memories = store.list_memories(limit=10)

    assert [memory.id for memory in memories] == [second.id, first.id]


def test_searching_memories_matches_content(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    target = store.add_memory("Antonio likes terminal tools", tags=[])
    store.add_memory("Something unrelated", tags=[])

    matches = store.search_memories("terminal", limit=10)

    assert [memory.id for memory in matches] == [target.id]


def test_searching_memories_matches_tags(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    target = store.add_memory("Keep answers concise", tags=["profile"])
    store.add_memory("Workspace note", tags=["project"])

    matches = store.search_memories("profile", limit=10)

    assert [memory.id for memory in matches] == [target.id]


def test_deleting_memory_removes_it(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    record = store.add_memory("delete me", tags=[])

    deleted = store.delete_memory(record.id)

    assert deleted is True
    assert store.get_memory(record.id) is None
    assert store.delete_memory(record.id) is False


def test_clearing_memories_removes_all_records(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    store.add_memory("first", tags=[])
    store.add_memory("second", tags=[])

    deleted = store.clear_memories()

    assert deleted == 2
    assert store.list_memories(limit=10) == []


def test_memory_initialize_adds_table_without_breaking_existing_sessions(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("session-1", "Existing session", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            ("session-1", "user", "hello", "2026-01-01T00:00:01Z"),
        )

    store = SQLiteMemoryStore(db_path)
    store.initialize()

    session = store.get_session("session-1")
    messages = store.load_messages("session-1")
    memory = store.add_memory("new memory", tags=[])
    assert session is not None
    assert session.title == "Existing session"
    assert [message.content for message in messages] == ["hello"]
    assert store.get_memory(memory.id) is not None


def test_context_builder_includes_relevant_memories_when_present(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    store.add_memory("My name is Antonio", tags=["profile"])
    relevant_memories = store.find_relevant_memories("What is my name?", limit=5)

    messages = build_chat_messages(
        DEFAULT_SYSTEM_PROMPT,
        [{"role": "assistant", "content": "Earlier reply."}],
        "What is my name?",
        relevant_memories=relevant_memories,
    )

    assert len(messages) == 4
    assert messages[1]["role"] == "system"
    assert "Relevant local memories:" in messages[1]["content"]
    assert "My name is Antonio" in messages[1]["content"]


def test_context_builder_does_not_include_memory_message_without_matches(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    store.add_memory("My favorite editor is Vim", tags=["prefs"])
    relevant_memories = store.find_relevant_memories("Explain SQLite transactions", limit=5)

    messages = build_chat_messages(DEFAULT_SYSTEM_PROMPT, [], "Explain SQLite transactions", relevant_memories)

    assert messages == [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": "Explain SQLite transactions"},
    ]


def test_memory_limit_caps_relevant_memory_injection(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    for index in range(4):
        store.add_memory(f"Project alpha note {index}", tags=["alpha"])

    relevant = store.find_relevant_memories("alpha project notes", limit=2)

    assert len(relevant) == 2


def test_agent_injects_relevant_memories_and_uses_name_safeguard(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    store.add_memory("My name is Antonio", tags=["profile"])
    provider = _RecordingProvider(answer="I am not sure.")
    agent = Agent(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        provider_manager=_RecordingProviderManager(provider),
        memory_store=store,
        max_memory_items=5,
    )

    result = asyncio.run(agent.ask("What is my name?"))

    assert result == "Your name is Antonio."
    assert len(provider.calls) == 1
    assert provider.calls[0][1]["role"] == "system"
    assert "Relevant local memories:" in provider.calls[0][1]["content"]
    assert "My name is Antonio" in provider.calls[0][1]["content"]


def test_memory_cli_supports_repeated_tags_and_clear_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli, "load_config", lambda: _config_for(tmp_path))

    add_result = runner.invoke(cli.app, ["memory", "add", "My name is Antonio", "--tag", "profile", "--tag", "user"])
    assert add_result.exit_code == 0
    memory_id = add_result.stdout.strip()
    store = _build_store(tmp_path)
    saved_memory = store.get_memory(memory_id)
    assert saved_memory is not None
    assert saved_memory.content == "My name is Antonio"
    assert saved_memory.tags == ("profile", "user")

    list_result = runner.invoke(cli.app, ["memory", "list"])
    assert list_result.exit_code == 0
    assert "Local memories" in list_result.stdout

    show_result = runner.invoke(cli.app, ["memory", "show", memory_id])
    assert show_result.exit_code == 0
    assert f"ID: {memory_id}" in show_result.stdout
    assert "My name is Antonio" in show_result.stdout

    search_content_result = runner.invoke(cli.app, ["memory", "search", "Antonio"])
    assert search_content_result.exit_code == 0
    assert "Memory search results for Antonio" in search_content_result.stdout

    search_tag_result = runner.invoke(cli.app, ["memory", "search", "profile"])
    assert search_tag_result.exit_code == 0
    assert "Memory search results for profile" in search_tag_result.stdout

    reject_clear_result = runner.invoke(cli.app, ["memory", "clear"], input="n\n")
    assert reject_clear_result.exit_code == 1
    assert "Aborted." in reject_clear_result.stdout

    delete_result = runner.invoke(cli.app, ["memory", "delete", memory_id])
    assert delete_result.exit_code == 0
    assert f"Deleted memory {memory_id}" in delete_result.stdout

    missing_delete_result = runner.invoke(cli.app, ["memory", "delete", memory_id])
    assert missing_delete_result.exit_code == 1
    assert f"Memory not found: {memory_id}" in missing_delete_result.output

    runner.invoke(cli.app, ["memory", "add", "temporary", "--tag", "scratch"])
    clear_result = runner.invoke(cli.app, ["memory", "clear", "--yes"])
    assert clear_result.exit_code == 0
    assert "Cleared 1 memories" in clear_result.stdout
