import asyncio
from pathlib import Path

from localmind.config.schema import DEFAULT_SYSTEM_PROMPT
from localmind.core.agent import Agent
from localmind.core.context import build_chat_messages
from localmind.core.session import SessionManager
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


def test_creating_sessions_persists_records(tmp_path: Path) -> None:
    manager = SessionManager(_build_store(tmp_path))

    session = manager.create()

    assert session.session_id
    assert session.record.title == "New session"
    assert manager.open(session.session_id).record.id == session.session_id


def test_adding_messages_persists_and_sets_title_from_first_user_message(tmp_path: Path) -> None:
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()

    session.append("user", "   Explain the current repository layout in one paragraph.   ")
    session.append("assistant", "It is a compact CLI-oriented Python package.")

    messages = session.load_messages()
    assert messages == [
        {"role": "user", "content": "   Explain the current repository layout in one paragraph.   "},
        {"role": "assistant", "content": "It is a compact CLI-oriented Python package."},
    ]
    assert session.record.title == "Explain the current repository layout in one paragraph."


def test_listing_sessions_returns_saved_sessions(tmp_path: Path) -> None:
    manager = SessionManager(_build_store(tmp_path))

    first = manager.create()
    second = manager.create()

    session_ids = {session.id for session in manager.list()}
    assert session_ids == {first.session_id, second.session_id}


def test_loading_recent_messages_returns_only_latest_messages_in_order(tmp_path: Path) -> None:
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()

    for index in range(1, 6):
        session.append("user" if index % 2 else "assistant", f"message-{index}")

    recent = session.load_recent_messages(3)

    assert recent == [
        {"role": "user", "content": "message-3"},
        {"role": "assistant", "content": "message-4"},
        {"role": "user", "content": "message-5"},
    ]


def test_context_builder_includes_system_prompt_first() -> None:
    messages = build_chat_messages(
        DEFAULT_SYSTEM_PROMPT,
        [{"role": "assistant", "content": "Earlier reply."}],
        "Current question",
    )

    assert messages[0] == {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
    assert messages[-1] == {"role": "user", "content": "Current question"}


def test_agent_history_limit_uses_only_recent_messages(tmp_path: Path) -> None:
    provider = _RecordingProvider()
    agent = Agent(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        provider_manager=_RecordingProviderManager(provider),
        max_history_messages=2,
    )
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()
    session.append("user", "old user")
    session.append("assistant", "old assistant")
    session.append("user", "recent user")
    session.append("assistant", "recent assistant")

    asyncio.run(agent.ask("current user", session=session))

    assert provider.calls == [
        [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": "recent user"},
            {"role": "assistant", "content": "recent assistant"},
            {"role": "user", "content": "current user"},
        ]
    ]


def test_agent_continues_session_with_system_history_and_current_user_in_order(tmp_path: Path) -> None:
    provider = _RecordingProvider()
    agent = Agent(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        provider_manager=_RecordingProviderManager(provider),
        max_history_messages=6,
    )
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()
    session.append("user", "Hello, my name is Antonio.")
    session.append("assistant", "Nice to meet you, Antonio.")

    asyncio.run(agent.ask("What is my name?", session=session))

    assert provider.calls == [
        [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": "Hello, my name is Antonio."},
            {"role": "assistant", "content": "Nice to meet you, Antonio."},
            {"role": "user", "content": "What is my name?"},
        ]
    ]


def test_agent_follow_up_name_safeguard_still_calls_provider_and_uses_history(tmp_path: Path) -> None:
    provider = _RecordingProvider(answer="I don't know your name.")
    agent = Agent(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        provider_manager=_RecordingProviderManager(provider),
        max_history_messages=6,
    )
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()
    session.append("user", "Hello, my name is Antonio.")
    session.append("assistant", "Nice to meet you, Antonio.")

    result = asyncio.run(agent.ask("What is my name?", session=session))

    assert result == "Your name is Antonio."
    assert len(provider.calls) == 1


def test_agent_does_not_duplicate_current_user_message_in_session_context(tmp_path: Path) -> None:
    provider = _RecordingProvider()
    agent = Agent(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        provider_manager=_RecordingProviderManager(provider),
        max_history_messages=8,
    )
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()
    session.append("user", "Earlier user")
    session.append("assistant", "Earlier assistant")

    asyncio.run(agent.ask("Current user", session=session))

    current_user_messages = [
        message
        for message in provider.calls[0]
        if message == {"role": "user", "content": "Current user"}
    ]
    assert len(current_user_messages) == 1


def test_session_message_timestamps_follow_insertion_order(tmp_path: Path) -> None:
    manager = SessionManager(_build_store(tmp_path))
    session = manager.create()

    first = session.append("user", "Hello")
    second = session.append("assistant", "Hi")

    assert first.created_at < second.created_at
