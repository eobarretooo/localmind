"""Plugin discovery and validation without execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from localmind.plugins.errors import PluginNotFoundError, PluginValidationError
from localmind.plugins.metadata import PluginMetadata
from localmind.plugins.state import PluginStateStore

_PLUGIN_MANIFEST_NAME = "plugin.yaml"
_SKIPPED_DIRECTORY_NAMES = {"__pycache__"}


@dataclass(slots=True, frozen=True)
class PluginRecord:
    metadata: PluginMetadata
    path: Path
    enabled: bool


class PluginManager:
    """Discover plugin manifests and resolve persisted state."""

    def __init__(self, plugin_directory: Path, state_store: PluginStateStore | None = None) -> None:
        self._plugin_directory = plugin_directory.expanduser()
        self._state_store = state_store

    @property
    def plugin_directory(self) -> Path:
        return self._plugin_directory

    def list_plugins(self) -> list[PluginRecord]:
        records: list[PluginRecord] = []
        for plugin_path in self._iter_plugin_directories():
            try:
                records.append(self._build_record(plugin_path))
            except PluginValidationError:
                continue
        records.sort(key=lambda record: record.metadata.name)
        return records

    def get_plugin(self, plugin_name: str) -> PluginRecord:
        for record in self.list_plugins():
            if record.metadata.name == plugin_name:
                return record
        raise PluginNotFoundError(f"Plugin not found: {plugin_name}")

    def validate_plugin_path(self, plugin_path: Path | str) -> PluginRecord:
        path = Path(plugin_path).expanduser().resolve()
        if not path.exists():
            raise PluginValidationError(f"Plugin path does not exist: {path}")
        if not path.is_dir():
            raise PluginValidationError(f"Plugin path is not a directory: {path}")
        return self._build_record(path)

    def _iter_plugin_directories(self) -> list[Path]:
        root = self._plugin_directory.resolve()
        if not root.exists() or not root.is_dir():
            return []

        plugin_directories: list[Path] = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in _SKIPPED_DIRECTORY_NAMES:
                continue
            try:
                resolved_child = child.resolve()
            except OSError:
                continue
            if resolved_child.parent != root:
                continue
            plugin_directories.append(resolved_child)
        return plugin_directories

    def _build_record(self, plugin_path: Path) -> PluginRecord:
        metadata = self._load_metadata(plugin_path)
        enabled = metadata.enabled
        if self._state_store is not None:
            persisted_enabled = self._state_store.get_enabled(metadata.name)
            if persisted_enabled is not None:
                enabled = persisted_enabled
        return PluginRecord(metadata=metadata, path=plugin_path.resolve(), enabled=enabled)

    def _load_metadata(self, plugin_path: Path) -> PluginMetadata:
        manifest_path = plugin_path / _PLUGIN_MANIFEST_NAME
        if not manifest_path.exists():
            raise PluginValidationError(
                f"Invalid plugin at {plugin_path.resolve()}",
                errors=[f"Missing {_PLUGIN_MANIFEST_NAME}"],
            )

        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PluginValidationError(
                f"Invalid plugin at {plugin_path.resolve()}",
                errors=[f"Failed to read {_PLUGIN_MANIFEST_NAME}: {exc}"],
            ) from exc
        except yaml.YAMLError as exc:
            raise PluginValidationError(
                f"Invalid plugin at {plugin_path.resolve()}",
                errors=[f"Invalid YAML in {_PLUGIN_MANIFEST_NAME}: {exc}"],
            ) from exc

        if not isinstance(raw, dict):
            raise PluginValidationError(
                f"Invalid plugin at {plugin_path.resolve()}",
                errors=[f"{_PLUGIN_MANIFEST_NAME} must contain a YAML mapping"],
            )

        try:
            return PluginMetadata.model_validate(cast(dict[str, Any], raw))
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ]
            raise PluginValidationError(f"Invalid plugin at {plugin_path.resolve()}", errors=errors) from exc
