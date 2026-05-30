"""Provider selection and connectivity checks."""

from __future__ import annotations

from dataclasses import dataclass

from localmind.config.schema import ProviderConfig
from localmind.llm.base import LLMProvider, ProviderConnectionError
from localmind.llm.openai_compatible import OpenAICompatibleProvider


@dataclass(slots=True)
class ProviderTestReport:
    base_url: str
    configured_model: str
    configured_model_available: bool
    models: list[str]


class ProviderManager:
    """Factory and thin manager around the selected provider."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._provider: LLMProvider | None = None

    def get_provider(self) -> LLMProvider:
        if self._provider is None:
            if self._config.type == "openai_compatible":
                self._provider = OpenAICompatibleProvider(self._config)
            else:
                raise RuntimeError(f"Unsupported provider type: {self._config.type}")
        return self._provider

    async def test_connection(self) -> ProviderTestReport:
        provider = self.get_provider()
        if not isinstance(provider, OpenAICompatibleProvider):
            raise RuntimeError("Connectivity checks are only implemented for OpenAI-compatible providers.")

        try:
            models = await provider.list_models()
        except ProviderConnectionError:
            raise
        except Exception as exc:
            raise ProviderConnectionError(str(exc)) from exc

        return ProviderTestReport(
            base_url=self._config.base_url,
            configured_model=self._config.model,
            configured_model_available=(self._config.model in models) if models else False,
            models=models,
        )
