"""Energy grid subsystem balancing consumption and production."""

from __future__ import annotations

import logging
import random
from typing import Any, Dict

from src.subsystems.base import SubsystemThread

logger = logging.getLogger(__name__)


class EnergyGrid(SubsystemThread):
    """Simulate dynamic energy load balancing across zones."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._zones = cfg.get("zones", 3)
        self._base_load = cfg.get("base_load_mw", 100)
        self._rng = random.Random(cfg.get("seed"))
        self._zone_loads: Dict[str, float] = {
            f"zone_{index}": float(self._base_load / max(self._zones, 1))
            for index in range(self._zones)
        }
        self._surplus = 0.0

    def on_start(self) -> None:
        logger.info("Energy subsystem initialised (zones=%d)", self._zones)

    def execute_tick(self) -> None:
        total_consumption = 0.0

        for zone, current_load in self._zone_loads.items():
            fluctuation = self._rng.uniform(-5.0, 5.0)
            new_load = max(current_load + fluctuation, 0.0)
            self._zone_loads[zone] = new_load
            total_consumption += new_load

        generation = self._base_load + self._rng.uniform(-10.0, 10.0)
        self._surplus = generation - total_consumption

        logger.debug(
            "Energy tick: generation=%.1fMW consumption=%.1fMW surplus=%.1fMW",
            generation,
            total_consumption,
            self._surplus,
        )

    @property
    def zone_loads(self) -> Dict[str, float]:
        return dict(self._zone_loads)

    @property
    def surplus(self) -> float:
        return self._surplus

