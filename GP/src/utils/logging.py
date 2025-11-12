"""Logging helpers for the simulation runtime."""

from __future__ import annotations

import logging
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def configure_logging(level: LogLevel) -> None:
    """Configure root logging for the application."""

    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s",
    )

