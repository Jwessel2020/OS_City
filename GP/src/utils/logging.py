"""Logging helpers for the simulation runtime."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def configure_logging(level: LogLevel, log_file: str | None = "logs/runtime.log") -> None:
    """Configure root logging for the application."""

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s",
        handlers=handlers,
    )

