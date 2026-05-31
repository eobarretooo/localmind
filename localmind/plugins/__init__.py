"""Plugin discovery and state foundation."""

from localmind.plugins.errors import PluginError, PluginNotFoundError, PluginValidationError
from localmind.plugins.manager import PluginManager, PluginRecord
from localmind.plugins.metadata import PLUGIN_NAME_PATTERN, PluginMetadata
from localmind.plugins.state import PluginStateStore

__all__ = [
    "PLUGIN_NAME_PATTERN",
    "PluginError",
    "PluginManager",
    "PluginMetadata",
    "PluginNotFoundError",
    "PluginRecord",
    "PluginStateStore",
    "PluginValidationError",
]
