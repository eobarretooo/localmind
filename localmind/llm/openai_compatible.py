"""OpenAI-compatible HTTP provider."""

from __future__ import annotations

from typing import Any

import httpx

from localmind.config.schema import ProviderConfig
from localmind.llm.base import LLMProvider, ProviderConnectionError


class OpenAICompatibleProvider(LLMProvider):
    """Minimal wrapper for chat completions and model listing."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    async def chat(self, messages: list[dict], stream: bool = False) -> str:
        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": stream,
        }

        async with self._client() as client:
            try:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
            except httpx.ConnectError as exc:
                raise ProviderConnectionError(self._connection_error_message()) from exc
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or exc.response.reason_phrase
                raise ProviderConnectionError(
                    f"OpenAI-compatible server returned HTTP {exc.response.status_code} for chat completions: {detail}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderConnectionError(f"Request to LLM server failed: {exc}") from exc

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderConnectionError("OpenAI-compatible server returned no choices for chat completion.")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderConnectionError("OpenAI-compatible server returned a response without message.content.")
        return content.strip()

    async def list_models(self) -> list[str]:
        async with self._client() as client:
            try:
                response = await client.get("/models")
                response.raise_for_status()
            except httpx.ConnectError as exc:
                raise ProviderConnectionError(self._connection_error_message()) from exc
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or exc.response.reason_phrase
                raise ProviderConnectionError(
                    f"OpenAI-compatible server returned HTTP {exc.response.status_code} for /models: {detail}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderConnectionError(f"Request to LLM server failed: {exc}") from exc

        data: dict[str, Any] = response.json()
        models = data.get("data")
        if not isinstance(models, list):
            return []
        result: list[str] = []
        for item in models:
            model_id = item.get("id") if isinstance(item, dict) else None
            if isinstance(model_id, str):
                result.append(model_id)
        return result

    def _client(self) -> httpx.AsyncClient:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return httpx.AsyncClient(
            base_url=self._config.base_url,
            headers=headers,
            timeout=self._config.timeout_seconds,
        )

    def _connection_error_message(self) -> str:
        return (
            "Could not connect to the configured OpenAI-compatible server at "
            f"{self._config.base_url}. Start llama.cpp server mode or update localmind.yaml."
        )
