import asyncio
import logging
from typing import Any

from localmind.config.schema import DEFAULT_SYSTEM_PROMPT, ProviderConfig
from localmind.core.agent import Agent
from localmind.llm.base import ProviderConnectionError
from localmind.llm.openai_compatible import OpenAICompatibleProvider
from localmind.utils.logging import configure_logging
import pytest


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _StubClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> "_StubClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def post(self, path: str, json: dict[str, Any]) -> _StubResponse:
        assert path == "/chat/completions"
        assert json["messages"]
        return _StubResponse(self._payload)


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


class _StubProviderManager:
    def get_provider(self) -> Any:
        raise AssertionError("provider access not expected during init")


def test_openai_compatible_provider_returns_only_stripped_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(config=ProviderConfig(model="test-model"))
    payload = {
        "choices": [
            {
                "message": {
                    "content": "  final answer  ",
                    "reasoning_content": "internal reasoning",
                }
            }
        ]
    }
    monkeypatch.setattr(provider, "_client", lambda: _StubClient(payload))

    result = asyncio.run(provider.chat([{"role": "user", "content": "hello"}]))

    assert result == "final answer"


def test_openai_compatible_provider_rejects_missing_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(config=ProviderConfig(model="test-model"))
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: _StubClient({"choices": [{"message": {"reasoning_content": "only reasoning"}}]}),
    )

    with pytest.raises(ProviderConnectionError, match="message.content"):
        asyncio.run(provider.chat([{"role": "user", "content": "hello"}]))


def test_agent_uses_default_prompt_when_configured_prompt_is_blank() -> None:
    agent = Agent(system_prompt="   ", provider_manager=_StubProviderManager())

    assert agent._system_prompt == DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_identifies_as_localmind_not_backend() -> None:
    assert "LocalMind" in DEFAULT_SYSTEM_PROMPT
    assert "not the raw model backend" in DEFAULT_SYSTEM_PROMPT
    assert "identify yourself as LocalMind" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_treats_user_name_as_user_information() -> None:
    assert "If the user shares personal information such as their name" in DEFAULT_SYSTEM_PROMPT
    assert "treat it as information about the user" in DEFAULT_SYSTEM_PROMPT
    assert "do not claim it as your own" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_requires_using_session_history_for_follow_ups() -> None:
    assert "Use the conversation history when answering follow-up questions." in DEFAULT_SYSTEM_PROMPT
    assert "answer from the session history" in DEFAULT_SYSTEM_PROMPT


def test_agent_sends_system_message_first_to_provider() -> None:
    provider = _RecordingProvider()
    agent = Agent(system_prompt=DEFAULT_SYSTEM_PROMPT, provider_manager=_RecordingProviderManager(provider))

    result = asyncio.run(agent.ask("Say hello in one short sentence."))

    assert result == "provider answer"
    assert len(provider.calls) == 1
    first_message = provider.calls[0][0]
    assert first_message["role"] == "system"
    assert "LocalMind" in first_message["content"]
    assert "identify yourself as LocalMind" in first_message["content"]


def test_agent_answers_common_identity_questions_as_localmind() -> None:
    provider = _RecordingProvider()
    agent = Agent(system_prompt=DEFAULT_SYSTEM_PROMPT, provider_manager=_RecordingProviderManager(provider))

    result = asyncio.run(agent.ask("What are you?"))

    assert result == "I am LocalMind, a local-first AI assistant running on your Linux machine."
    assert provider.calls == []


def test_agent_acknowledges_common_user_name_introductions_without_using_provider() -> None:
    provider = _RecordingProvider()
    agent = Agent(system_prompt=DEFAULT_SYSTEM_PROMPT, provider_manager=_RecordingProviderManager(provider))

    result = asyncio.run(agent.ask("Hello, my name is Antonio."))

    assert result == "Nice to meet you, Antonio."
    assert provider.calls == []


def test_configure_logging_keeps_http_clients_quiet_by_default() -> None:
    configure_logging("WARNING")

    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
