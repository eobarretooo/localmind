"""Plugin-related errors."""

from __future__ import annotations


class PluginError(Exception):
    """Base class for plugin foundation errors."""


class PluginNotFoundError(PluginError):
    """Raised when a named plugin cannot be discovered."""


class PluginValidationError(PluginError):
    """Raised when plugin metadata is missing or invalid."""

    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        self.message = message
        self.errors = errors or []
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if not self.errors:
            return self.message
        details = "\n".join(f"- {error}" for error in self.errors)
        return f"{self.message}\n{details}"
