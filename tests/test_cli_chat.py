import asyncio
from pathlib import Path

import pytest
from rich.console import Console

from localmind.app import cli
from localmind.core.session import Session, SessionManager
from localmind.memory.sqlite import SQLiteMemoryStore


class _FailIfCalledAgent:
    async def ask(self, user_message: str, session: Session | None = None) -> str:
        raise AssertionError(f"agent.ask should not be called for internal exit command: {user_message}")


class _RecordingAgent:
    def __init__(self, reply: str = "stub reply") -> None:
        self.reply = reply
        self.calls: list[str] = []

    async def ask(self, user_message: str, session: Session | None = None) -> str:
        self.calls.append(user_message)
        if session is not None:
            session.append("user", user_message)
            session.append("assistant", self.reply)
        return self.reply


class _StubRuntime:
    def __init__(self, session: Session, agent: object | None = None) -> None:
        self.session = session
        self.agent = agent if agent is not None else _FailIfCalledAgent()

    async def __aenter__(self) -> "_StubRuntime":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _build_store(tmp_path: Path) -> SQLiteMemoryStore:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    return store


@pytest.mark.parametrize("message", ["exit", "quit", "/exit", "/quit", ":q"])
def test_internal_exit_commands_stop_chat_without_saving_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    message: str,
) -> None:
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()
    prompts = iter([message])

    monkeypatch.setattr(cli, "build_runtime", lambda **_: _StubRuntime(session))
    monkeypatch.setattr(cli.typer, "prompt", lambda _: next(prompts))
    monkeypatch.setattr(cli, "console", Console(record=True, width=120))

    asyncio.run(cli._chat_loop(create_session=True))

    reopened = manager.open(session.session_id)
    assert reopened.load_messages() == []


@pytest.mark.parametrize("message", ["/exit", "/quit"])
def test_slash_exit_commands_are_internal_commands(message: str) -> None:
    assert cli._is_internal_exit_command(message)


def test_chat_loop_saves_only_non_exit_exchange_and_creates_no_exit_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()
    agent = _RecordingAgent(reply="Hello there.")
    prompts = iter(["Hello", "/exit"])

    monkeypatch.setattr(cli, "build_runtime", lambda **_: _StubRuntime(session, agent=agent))
    monkeypatch.setattr(cli.typer, "prompt", lambda _: next(prompts))
    monkeypatch.setattr(cli, "console", Console(record=True, width=120))

    asyncio.run(cli._chat_loop(create_session=True))

    reopened = manager.open(session.session_id)
    assert reopened.load_messages() == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hello there."},
    ]
    assert agent.calls == ["Hello"]


def test_chat_startup_text_mentions_all_internal_exit_commands() -> None:
    assert cli._CHAT_STARTUP_TEXT == "Type 'exit', 'quit', '/exit', '/quit', or ':q' to leave."
