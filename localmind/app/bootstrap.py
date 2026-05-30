"""Runtime bootstrap helpers."""

from __future__ import annotations

from pathlib import Path

from localmind.config.loader import dump_config, load_config
from localmind.config.schema import AppConfig
from localmind.core.agent import Agent
from localmind.core.context import AppContext
from localmind.core.lifecycle import ApplicationLifecycle
from localmind.core.session import Session
from localmind.llm.manager import ProviderManager
from localmind.memory.sqlite import SQLiteMemoryStore
from localmind.utils.logging import configure_logging


def build_runtime(config_path: Path | None = None) -> ApplicationLifecycle:
    """Build the application runtime with configured services."""
    config = load_config(config_path)
    configure_logging(config.logging.level)
    memory = SQLiteMemoryStore(config.memory.db_path)
    provider_manager = ProviderManager(config.provider)
    session = Session(memory=memory)
    agent = Agent(system_prompt=config.app.system_prompt, provider_manager=provider_manager)
    context = AppContext(
        config=config,
        provider_manager=provider_manager,
        memory=memory,
        session=session,
        agent=agent,
    )
    return ApplicationLifecycle(context)


def write_default_config(target: Path, config: AppConfig) -> None:
    """Write a YAML config file for local overrides."""
    target.write_text(dump_config(config, redact_secrets=False), encoding="utf-8")
