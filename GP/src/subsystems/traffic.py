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
        self._avg_speed = 40.0
        self._avg_wait_min = 2.0
        self._incidents_this_tick = 0
        self._total_incidents = 0
        self._vehicles = 0
        self._ev_demand_mwh = 0.0
        self._signal_efficiency = 1.0

    def on_start(self) -> None:
        logger.info(
            "Traffic subsystem initialised (junctions=%d, vehicles/tick=%d)",
            self._junctions,
            self._vehicles_per_tick,
        )

    def execute_tick(self) -> None:
        energy_surplus = float(self.get_metric("energy", "surplus_mw", 0.0))
        emergency_units = float(self.get_metric("emergency", "active_units", 0.0))

        variability = self._rng.gauss(0, self._vehicles_per_tick * 0.1)
        vehicles = max(int(self._vehicles_per_tick + variability), 0)

        # Energy shortages reduce signal efficiency, emergency roadblocks reduce capacity
        self._signal_efficiency = max(0.6, 1.0 + min(energy_surplus, 0) / 150.0)
        self._signal_efficiency -= min(emergency_units * 0.03, 0.2)

        base_capacity = self._junctions * 12
        effective_capacity = max(base_capacity * self._signal_efficiency, 1)
        congestion_ratio = vehicles / effective_capacity

        # Smooth congestion changes
        occupancy_ratio = min(congestion_ratio, 1.5)
        self._history.append(occupancy_ratio)
        self._congestion_index = sum(self._history) / len(self._history)

        # Derive operational metrics
        congestion_factor = min(self._congestion_index, 1.4)
        self._avg_speed = max(8.0, 55.0 * (1.0 - congestion_factor * 0.55))
        self._avg_wait_min = max(0.5, 1.5 + 6.0 * (congestion_factor - 0.5))
        self._avg_wait_min = max(0.5, self._avg_wait_min)

        incident_probability = 0.02 + max(self._congestion_index - 0.85, 0) * 0.2
        self._incidents_this_tick = 0
        if self._rng.random() < incident_probability:
            self._incidents_this_tick = self._rng.randint(1, 3)
            self._total_incidents += self._incidents_this_tick

        # Estimate EV charging demand influenced by slower traffic (more idle time)
        idle_factor = 1.0 - min(self._avg_speed / 50.0, 1.0)
        self._ev_demand_mwh = round(vehicles * idle_factor * 0.02, 3)

        self._vehicles = vehicles

        logger.debug(
            (
                "Traffic tick: vehicles=%d congestion_index=%.2f avg_speed=%.1f "
                "incidents=%d signal_eff=%.2f"
            ),
            vehicles,
            self._congestion_index,
            self._avg_speed,
            self._incidents_this_tick,
            self._signal_efficiency,
        )

    def collect_metrics(self) -> dict[str, Any]:
        return {
            "vehicles": self._vehicles,
            "avg_speed_kmh": round(self._avg_speed, 2),
            "avg_wait_min": round(self._avg_wait_min, 2),
            "congestion_index": round(self._congestion_index, 3),
            "incidents": self._incidents_this_tick,
            "total_incidents": self._total_incidents,
            "signal_efficiency": round(self._signal_efficiency, 3),
            "ev_charging_demand_mwh": self._ev_demand_mwh,
        }

