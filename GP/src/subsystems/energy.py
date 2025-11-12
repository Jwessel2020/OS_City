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
        self._generation = self._base_load
        self._consumption = self._base_load
        self._renewables = self._base_load * cfg.get("renewable_share", 0.35)
        self._storage_capacity = cfg.get("storage_capacity_mwh", 250.0)
        self._storage_level = self._storage_capacity * cfg.get("initial_storage_pct", 0.45)
        self._grid_losses = 0.0
        self._price_index = 1.0
        self._demand_response_active = False

    def on_start(self) -> None:
        logger.info("Energy subsystem initialised (zones=%d)", self._zones)

    def execute_tick(self) -> None:
        traffic_ev = float(self.get_metric("traffic", "ev_charging_demand_mwh", 0.0))
        waste_energy = float(self.get_metric("waste", "fleet_energy_mwh", 0.0))
        emergency_energy = float(self.get_metric("emergency", "grid_demand_mwh", 0.0))

        distributed_additional = traffic_ev + waste_energy + emergency_energy
        per_zone_extra = distributed_additional / max(self._zones, 1)

        total_consumption = 0.0

        for zone, current_load in self._zone_loads.items():
            fluctuation = self._rng.uniform(-6.0, 6.0)
            new_load = max(current_load + fluctuation + per_zone_extra, 10.0)
            self._zone_loads[zone] = new_load
            total_consumption += new_load

        total_consumption += traffic_ev + waste_energy + emergency_energy
        weather_factor = 0.8 + self._rng.uniform(-0.18, 0.22)
        self._renewables = max(0.0, self._base_load * weather_factor * 0.4)
        thermal_generation = max(self._base_load * 0.6 + self._rng.uniform(-8.0, 12.0), 20.0)
        self._generation = self._renewables + thermal_generation

        self._grid_losses = total_consumption * 0.05
        net_balance = self._generation - (total_consumption + self._grid_losses)
        self._surplus = net_balance

        if net_balance >= 0:
            energy_to_store = min(net_balance, self._storage_capacity - self._storage_level)
            self._storage_level += energy_to_store
            self._surplus -= energy_to_store
        else:
            discharge = min(-net_balance, self._storage_level)
            self._storage_level -= discharge
            self._surplus += discharge

        utilisation_ratio = total_consumption / max(self._generation, 1.0)
        self._price_index = 0.9 + utilisation_ratio * 0.6
        self._demand_response_active = utilisation_ratio > 0.92

        logger.debug(
            "Energy tick: generation=%.1fMW consumption=%.1fMW surplus=%.1fMW storage=%.1fMWh",
            self._generation,
            total_consumption,
            self._surplus,
            self._storage_level,
        )

        self._consumption = total_consumption

    def collect_metrics(self) -> dict[str, Any]:
        renewable_share = self._renewables / max(self._generation, 1.0)
        blackout_risk = max(0.0, 1.0 - (self._storage_level / max(self._storage_capacity, 1.0) + self._surplus / 50.0))

        return {
            "generation_mw": round(self._generation, 2),
            "consumption_mw": round(self._consumption, 2),
            "surplus_mw": round(self._surplus, 2),
            "renewable_ratio": round(renewable_share, 3),
            "storage_mwh": round(self._storage_level, 2),
            "demand_response": self._demand_response_active,
            "losses_mw": round(self._grid_losses, 2),
            "price_index": round(self._price_index, 3),
            "blackout_risk": round(min(max(blackout_risk, 0.0), 1.0), 3),
        }

