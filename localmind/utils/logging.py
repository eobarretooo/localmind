"""Logging setup helpers."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    resolved_level = getattr(logging, level.upper(), logging.WARNING)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        logging.basicConfig(level=resolved_level)
    root_logger.setLevel(resolved_level)

    # Keep transport libraries quiet unless the user opts into noisier logs.
    for logger_name in ("httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
