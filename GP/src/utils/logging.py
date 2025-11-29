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

    # Explicitly silence Werkzeug (Flask) logs to clean up output
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s",
        handlers=handlers,
        force=True
    )
    
    # Force 'src' logger to INFO (or DEBUG) and ensure it uses our handlers
    src_logger = logging.getLogger("src")
    src_logger.setLevel(logging.DEBUG)
    for handler in handlers:
        if handler not in src_logger.handlers:
            src_logger.addHandler(handler)
    src_logger.propagate = False  # Prevent double logging if root also logs

    # Add a specific trace logger for educational output
    trace_logger = logging.getLogger("trace")
    trace_logger.setLevel(logging.INFO)
    # Ensure trace logs go to the same handlers
    trace_logger.propagate = True

