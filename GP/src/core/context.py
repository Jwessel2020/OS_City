"""Thread-safe shared context for cross-subsystem coordination."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Tuple


class CityContext:
    """Stores the latest snapshot for each subsystem with synchronisation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: Dict[str, Tuple[int, dict[str, Any]]] = {}
        self._controls: dict[str, Any] = {}

    def update(self, subsystem: str, tick: int, metrics: dict[str, Any]) -> None:
        """Update the stored metrics for a subsystem."""

        with self._lock:
            self._state[subsystem] = (tick, dict(metrics))

    def update_controls(self, controls: dict[str, Any]) -> None:
        """Update control parameters shared with subsystems."""

        with self._lock:
            self._controls.update(controls)

    def get_control(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._controls.get(key, default)

    def get_latest(self, subsystem: str) -> Optional[Tuple[int, dict[str, Any]]]:
        """Retrieve the latest metrics for a subsystem."""

        with self._lock:
            return self._state.get(subsystem)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a shallow copy of the entire context."""

        with self._lock:
            return {name: dict(metrics) for name, (_, metrics) in self._state.items()}

