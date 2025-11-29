"""Dedicated tracing module for educational data flow visualization."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_file_path = Path("logs/educational_trace.log")

def init_trace() -> None:
    """Initialize the trace file."""
    _file_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(_file_path, "w", encoding="utf-8") as f:
            f.write(f"--- SIMULATION DATA FLOW TRACE STARTED AT {time.ctime()} ---\n")
            f.write("Format: [TIME] [CATEGORY] Message | Payload\n\n")

def log_event(category: str, message: str, payload: Any = None) -> None:
    """Write a high-visibility log entry to stdout and file."""
    timestamp = time.strftime("%H:%M:%S")
    
    # Format specifically for readability
    text = f"[{timestamp}] [{category.upper():<12}] {message}"
    if payload:
        # Pretty print dictionary payloads slightly
        text += f" | Data: {str(payload)}"
    
    # Force print to console (bypasses logging config)
    print(text)
    
    # Append to file
    try:
        with _lock:
            with open(_file_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
    except Exception:
        pass  # Don't crash if file access fails

