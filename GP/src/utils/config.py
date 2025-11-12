"""Configuration helpers for the simulation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_simulation_config(path: Path) -> dict[str, Any]:
    """Load a simulation configuration from a JSON file."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"Simulation configuration must be a JSON object, got {type(data)!r}"
        raise TypeError(msg)
    return data

