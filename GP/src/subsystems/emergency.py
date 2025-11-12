"""Emergency response subsystem monitoring and dispatching incidents."""

from __future__ import annotations

import logging
import random
from typing import Any

from src.subsystems.base import SubsystemThread

logger = logging.getLogger(__name__)


class EmergencyUnit(SubsystemThread):
    """Model emergency incident processing."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._priority_threshold = cfg.get("priority_threshold", 0.6)
        self._rng = random.Random(cfg.get("seed"))
        self._open_incidents = 0
        self._resolved_incidents = 0
        self._units_available = cfg.get("response_units", 6)
        self._resolved_this_tick = 0
        self._active_units = 0
        self._avg_response_min = 6.0
        self._grid_demand_mwh = 0.0

    def execute_tick(self) -> None:
        congestion = float(self.get_metric("traffic", "congestion_index", 0.5))
        avg_speed = float(self.get_metric("traffic", "avg_speed_kmh", 35.0))
        blackout_risk = float(self.get_metric("energy", "blackout_risk", 0.2))
        waste_backlog = float(self.get_metric("waste", "pending_requests", 0))

        incident_pressure = 0.4 + congestion * 1.6 + blackout_risk * 2.0 + waste_backlog * 0.03
        incident_pressure *= self._rng.uniform(0.7, 1.3)
        expected_incidents = max(0.0, incident_pressure)
        new_incidents = int(expected_incidents)
        if self._rng.random() < (expected_incidents - new_incidents):
            new_incidents += 1
        if bool(self.get_control("emergency_override", False)):
            new_incidents += self._rng.randint(1, 2)

        if new_incidents:
            self._open_incidents += new_incidents
            logger.debug("Emergency tick: registered %d new incidents", new_incidents)

        if self._open_incidents:
            congestion_penalty = 1.0 + max(congestion - 0.8, 0) * 0.8
            speed_factor = max(avg_speed / 45.0, 0.4)
            dispatch_capacity = max(int(self._units_available * speed_factor / congestion_penalty), 1)
            self._active_units = min(dispatch_capacity, self._units_available)

            resolution_rate = self._priority_threshold + self._rng.uniform(-0.15, 0.25)
            max_resolvable = int(self._active_units * resolution_rate)
            self._resolved_this_tick = min(self._open_incidents, max(max_resolvable, 0))
            self._open_incidents -= self._resolved_this_tick
            self._resolved_incidents += self._resolved_this_tick

            self._avg_response_min = max(
                5.0,
                4.5 + congestion * 6.0 + blackout_risk * 5.0 - avg_speed * 0.05,
            )
            self._grid_demand_mwh = round(self._active_units * 0.04, 3)

            if self._resolved_this_tick:
                logger.debug(
                    "Emergency tick: resolved %d incidents (open=%d)",
                    self._resolved_this_tick,
                    self._open_incidents,
                )
        else:
            self._resolved_this_tick = 0
            self._active_units = 0
            self._grid_demand_mwh = 0.0

    def collect_metrics(self) -> dict[str, Any]:
        severity_index = min(1.0, self._open_incidents / max(self._units_available * 2, 1))
        return {
            "open_incidents": self._open_incidents,
            "resolved_total": self._resolved_incidents,
            "resolved_this_tick": self._resolved_this_tick,
            "active_units": self._active_units,
            "avg_response_min": round(self._avg_response_min, 2),
            "severity_index": round(severity_index, 3),
            "grid_demand_mwh": self._grid_demand_mwh,
        }

