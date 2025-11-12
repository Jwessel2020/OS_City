"""Thread-safe shared context for cross-subsystem coordination."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Tuple


class CityContext:
    """Stores the latest snapshot for each subsystem with synchronisation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: Dict[str, Tuple[int, dict[str, Any]]] = {}

    def update(self, subsystem: str, tick: int, metrics: dict[str, Any]) -> None:
        """Update the stored metrics for a subsystem."""

        with self._lock:
            self._state[subsystem] = (tick, dict(metrics))

    def get_latest(self, subsystem: str) -> Optional[Tuple[int, dict[str, Any]]]:
        """Retrieve the latest metrics for a subsystem."""

        with self._lock:
            return self._state.get(subsystem)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a shallow copy of the entire context."""

        with self._lock:
            return {name: dict(metrics) for name, (_, metrics) in self._state.items()}

