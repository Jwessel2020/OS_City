"""Waste operations subsystem managing collection routes."""

from __future__ import annotations

import logging
import random
from collections import deque
from typing import Any, Deque

from src.subsystems.base import SubsystemThread

logger = logging.getLogger(__name__)


class WasteOps(SubsystemThread):
    """Simulate waste collection vehicle dispatch."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._fleet_size = cfg.get("fleet_size", 4)
        self._requests_per_tick = cfg.get("requests_per_tick", 5)
        self._rng = random.Random(cfg.get("seed"))
        self._pending_requests: Deque[int] = deque()
        self._served_requests_total = 0
        self._served_this_tick = 0
        self._avg_route_km = 0.0
        self._fuel_liters = 0.0
        self._recycling_ratio = 0.4
        self._fleet_energy_mwh = 0.0

    def execute_tick(self) -> None:
        congestion = float(self.get_metric("traffic", "congestion_index", 0.5))
        avg_speed = float(self.get_metric("traffic", "avg_speed_kmh", 35.0))
        energy_price = float(self.get_metric("energy", "price_index", 1.0))

        seasonal_variation = self._rng.uniform(-1, 2)
        new_requests = max(0, int(self._requests_per_tick + seasonal_variation + congestion * 4))
        for _ in range(new_requests):
            self._pending_requests.append(self._rng.randint(1, 1000))

        congestion_penalty = 1.0 - min(congestion, 1.2) * 0.4
        effective_speed = max(avg_speed * congestion_penalty, 12.0)
        service_capacity = max(int((effective_speed / 25.0) * self._fleet_size), 1)

        active_fleet = min(self._fleet_size, len(self._pending_requests), service_capacity)
        self._served_this_tick = 0
        for _ in range(active_fleet):
            self._pending_requests.popleft()
            self._served_requests_total += 1
            self._served_this_tick += 1

        route_variation = self._rng.uniform(6.0, 12.0)
        self._avg_route_km = round(route_variation * max(active_fleet, 1) * max(1.0, 1.2 - congestion_penalty), 2)
        diesel_mix = 1.0 - min(energy_price / 3.0, 0.6)
        self._fuel_liters = round(self._avg_route_km * (0.3 + 0.6 * diesel_mix), 2)
        self._fleet_energy_mwh = round(self._avg_route_km * (1 - diesel_mix) * 0.015, 3)

        recycling_base = 0.35 + self._rng.uniform(-0.05, 0.07)
        congestion_penalty_recycle = 0.05 * max(congestion - 0.7, 0)
        self._recycling_ratio = max(0.2, min(0.75, recycling_base - congestion_penalty_recycle))

        backlog = len(self._pending_requests)
        logger.debug(
            "Waste tick: new_requests=%d served=%d backlog=%d routes_km=%.1f",
            new_requests,
            self._served_this_tick,
            backlog,
            self._avg_route_km,
        )

    def collect_metrics(self) -> dict[str, Any]:
        return {
            "pending_requests": len(self._pending_requests),
            "served_this_tick": self._served_this_tick,
            "served_total": self._served_requests_total,
            "avg_route_km": self._avg_route_km,
            "fuel_liters": self._fuel_liters,
            "recycling_ratio": round(self._recycling_ratio, 3),
            "fleet_energy_mwh": self._fleet_energy_mwh,
        }

