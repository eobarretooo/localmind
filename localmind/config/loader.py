"""Config file discovery and YAML serialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from localmind.config.schema import AppConfig

LOCAL_CONFIG_PATH = Path.cwd() / "localmind.yaml"
GLOBAL_CONFIG_PATH = Path("~/.config/localmind/config.yaml").expanduser()


def resolve_config_path(explicit_path: Path | None = None) -> Path | None:
    """Resolve config file using the requested precedence."""
    if explicit_path is not None:
        return explicit_path.expanduser()
    if LOCAL_CONFIG_PATH.exists():
        return LOCAL_CONFIG_PATH
    if GLOBAL_CONFIG_PATH.exists():
        return GLOBAL_CONFIG_PATH
    return None


def load_config(explicit_path: Path | None = None) -> AppConfig:
    """Load config from disk or return defaults when no file exists."""
    config_path = resolve_config_path(explicit_path)
    if config_path is None:
        return AppConfig()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise RuntimeError(f"Failed to read config file {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Invalid YAML in config file {config_path}: {exc}") from exc

    try:
        return AppConfig.model_validate(raw)
    except Exception as exc:
        raise RuntimeError(f"Invalid config in {config_path}: {exc}") from exc


def dump_config(config: AppConfig, redact_secrets: bool = True) -> str:
    """Serialize config to YAML, optionally redacting secrets."""
    payload: dict[str, Any] = config.model_dump(mode="json")
    if redact_secrets and payload["provider"].get("api_key"):
        payload["provider"]["api_key"] = "***REDACTED***"
    return yaml.safe_dump(payload, sort_keys=False)
