"""Traffic management subsystem simulating junction congestion."""

from __future__ import annotations

import logging
import random
from collections import deque
from typing import Any, Deque

from src.subsystems.base import SubsystemThread

logger = logging.getLogger(__name__)


class TrafficManager(SubsystemThread):
    """Maintain traffic flow metrics across city junctions."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._rng = random.Random(cfg.get("seed"))
        self._junctions = cfg.get("junctions", 8)
        self._vehicles_per_tick = cfg.get("vehicles_per_tick", 30)
        self._history: Deque[float] = deque(maxlen=20)
        self._congestion_index = 0.0

    def on_start(self) -> None:
        logger.info(
            "Traffic subsystem initialised (junctions=%d, vehicles/tick=%d)",
            self._junctions,
            self._vehicles_per_tick,
        )

    def execute_tick(self) -> None:
        vehicles = self._vehicles_per_tick + self._rng.randint(-5, 5)
        occupancy_ratio = max(vehicles, 0) / max(self._junctions * 10, 1)

        # Simple smoothing to emulate congestion build-up
        self._history.append(occupancy_ratio)
        self._congestion_index = sum(self._history) / len(self._history)

        logger.debug(
            "Traffic tick: vehicles=%d congestion_index=%.2f",
            vehicles,
            self._congestion_index,
        )

    @property
    def congestion_index(self) -> float:
        return self._congestion_index

