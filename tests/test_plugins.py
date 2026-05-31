from pathlib import Path

import pytest
from typer.testing import CliRunner

from localmind.app import cli
from localmind.config.schema import AppConfig
from localmind.memory.sqlite import SQLiteMemoryStore
from localmind.plugins import PluginManager, PluginStateStore
from localmind.plugins.errors import PluginNotFoundError, PluginValidationError


def _config_for(tmp_path: Path, plugin_dir: Path) -> AppConfig:
    return AppConfig.model_validate(
        {
            "memory": {"db_path": str(tmp_path / "memory.sqlite3")},
            "plugins": {"directory": str(plugin_dir)},
        }
    )


def _build_store(tmp_path: Path) -> SQLiteMemoryStore:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    return store


def test_valid_plugin_metadata_parsing() -> None:
    plugin = PluginManager(Path("/root/localmind/plugins")).validate_plugin_path(Path("/root/localmind/plugins/hello_world"))

    assert plugin.metadata.name == "hello_world"
    assert plugin.metadata.version == "0.1.0"
    assert plugin.metadata.commands == ["hello"]
    assert plugin.enabled is False


def test_missing_plugin_yaml_validation_error(tmp_path: Path) -> None:
    plugin_path = tmp_path / "missing_manifest"
    plugin_path.mkdir()

    with pytest.raises(PluginValidationError, match="Missing plugin.yaml"):
        PluginManager(tmp_path).validate_plugin_path(plugin_path)


def test_invalid_plugin_yaml_validation_error(tmp_path: Path) -> None:
    plugin_path = tmp_path / "bad_plugin"
    plugin_path.mkdir()
    (plugin_path / "plugin.yaml").write_text("name: Invalid Name\nversion: ''\ndescription: ok\n", encoding="utf-8")

    with pytest.raises(PluginValidationError) as exc_info:
        PluginManager(tmp_path).validate_plugin_path(plugin_path)

    assert "name: Value error" in str(exc_info.value)
    assert "entrypoint: Field required" in str(exc_info.value)


def test_plugin_discovery_finds_hello_world() -> None:
    plugins = PluginManager(Path("/root/localmind/plugins")).list_plugins()

    assert [plugin.metadata.name for plugin in plugins] == ["hello_world"]


def test_plugin_discovery_skips_hidden_folders(tmp_path: Path) -> None:
    hidden = tmp_path / ".hidden_plugin"
    hidden.mkdir()
    (hidden / "plugin.yaml").write_text(
        "name: hidden_plugin\nversion: 0.1.0\ndescription: hidden\nentrypoint: main:Hidden\n",
        encoding="utf-8",
    )
    visible = tmp_path / "visible_plugin"
    visible.mkdir()
    (visible / "plugin.yaml").write_text(
        "name: visible_plugin\nversion: 0.1.0\ndescription: visible\nentrypoint: main:Visible\n",
        encoding="utf-8",
    )

    plugins = PluginManager(tmp_path).list_plugins()

    assert [plugin.metadata.name for plugin in plugins] == ["visible_plugin"]


def test_plugins_list_command_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    hello = plugin_dir / "hello_world"
    hello.mkdir()
    (hello / "plugin.yaml").write_text(
        "name: hello_world\nversion: 0.1.0\ndescription: Example plugin\nauthor: LocalMind\nentrypoint: main:Hello\ncommands: [hello]\ntools: []\nenabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "load_config", lambda: _config_for(tmp_path, plugin_dir))

    result = runner.invoke(cli.app, ["plugins", "list"])

    assert result.exit_code == 0
    assert "Discovered plugins" in result.stdout
    assert "hello_world" in result.stdout
    assert "disabled" in result.stdout


def test_plugins_info_command_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli, "load_config", lambda: _config_for(tmp_path, Path("/root/localmind/plugins")))

    result = runner.invoke(cli.app, ["plugins", "info", "hello_world"])

    assert result.exit_code == 0
    assert "Name: hello_world" in result.stdout
    assert "Version: 0.1.0" in result.stdout
    assert "Declared commands: hello" in result.stdout


def test_plugins_info_missing_plugin_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli, "load_config", lambda: _config_for(tmp_path, Path("/root/localmind/plugins")))

    result = runner.invoke(cli.app, ["plugins", "info", "missing"])

    assert result.exit_code == 1
    assert "Plugin not found: missing" in result.output


def test_enable_plugin_stores_enabled_state(tmp_path: Path) -> None:
    state_store = PluginStateStore(_build_store(tmp_path))

    state_store.set_enabled("hello_world", True)

    assert state_store.get_enabled("hello_world") is True


def test_disable_plugin_stores_disabled_state(tmp_path: Path) -> None:
    state_store = PluginStateStore(_build_store(tmp_path))
    state_store.set_enabled("hello_world", True)

    state_store.set_enabled("hello_world", False)

    assert state_store.get_enabled("hello_world") is False


def test_enabled_disabled_state_persists(tmp_path: Path) -> None:
    first_store = _build_store(tmp_path)
    PluginStateStore(first_store).set_enabled("hello_world", True)

    second_store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    second_store.initialize()

    assert PluginStateStore(second_store).get_enabled("hello_world") is True


def test_plugin_validation_does_not_execute_main_py(tmp_path: Path) -> None:
    plugin_path = tmp_path / "safe_plugin"
    plugin_path.mkdir()
    (plugin_path / "plugin.yaml").write_text(
        "name: safe_plugin\nversion: 0.1.0\ndescription: Safe validation\nentrypoint: main:SafePlugin\n",
        encoding="utf-8",
    )
    (plugin_path / "main.py").write_text("raise RuntimeError('should not execute')\n", encoding="utf-8")

    plugin = PluginManager(tmp_path).validate_plugin_path(plugin_path)

    assert plugin.metadata.name == "safe_plugin"


def test_plugins_enable_disable_commands_persist_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli, "load_config", lambda: _config_for(tmp_path, Path("/root/localmind/plugins")))

    enable_result = runner.invoke(cli.app, ["plugins", "enable", "hello_world"])
    disable_result = runner.invoke(cli.app, ["plugins", "disable", "hello_world"])
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()

    assert enable_result.exit_code == 0
    assert "Enabled plugin hello_world" in enable_result.stdout
    assert disable_result.exit_code == 0
    assert "Disabled plugin hello_world" in disable_result.stdout
    assert store.get_plugin_enabled("hello_world") is False


def test_plugin_manager_missing_plugin_raises_not_found() -> None:
    with pytest.raises(PluginNotFoundError, match="Plugin not found: missing"):
        PluginManager(Path("/root/localmind/plugins")).get_plugin("missing")
