"""Energy grid subsystem balancing consumption and production."""

from __future__ import annotations

import logging
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List

from src.subsystems.base import SubsystemThread
from src.utils.weather import WeatherEngine

logger = logging.getLogger(__name__)


@dataclass
class TransmissionLine:
    identifier: str
    origin: str
    destination: str
    capacity_mw: float
    loss_pct: float


class EnergyGrid(SubsystemThread):
    """Simulate dynamic energy load balancing across geo-tagged zones."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._rng = random.Random(cfg.get("seed"))
        self._base_load = cfg.get("base_load_mw", 140.0)
        self._base_price = float(cfg.get("base_price_mwh", 68.0))
        self._pricing_cfg = cfg.get("pricing", {}) or {}
        self._local_costs = cfg.get("local_costs", {}) or {}
        self._storage_capacity = float(cfg.get("storage_capacity_mwh", 320.0))
        pct = float(cfg.get("initial_storage_pct", 0.5))
        self._storage_level = self._storage_capacity * max(0.0, min(pct, 1.0))
        self._storage_input_cumulative = 1e-6
        self._storage_output_cumulative = 1e-6
        self._zones = self._load_zones(cfg)
        self._lines = self._load_lines(cfg, self._zones)
        self._adjacency = self._build_adjacency()
        self._grid_losses = 0.0
        self._demand_response_active = False
        self._latest_metrics: dict[str, Any] = {}
        self._history: dict[str, Deque[float]] = {
            "transmission_efficiency": deque(maxlen=96),
            "renewable_ratio": deque(maxlen=96),
            "storage_efficiency": deque(maxlen=96),
            "avg_price": deque(maxlen=96),
            "carbon_intensity": deque(maxlen=96),
        }
        self._weather = WeatherEngine(cfg.get("weather_profile"))

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def _load_zones(self, cfg: dict[str, Any]) -> Dict[str, dict[str, Any]]:
        raw_zones = cfg.get("zones")
        zones: Dict[str, dict[str, Any]] = {}
        if isinstance(raw_zones, list) and raw_zones:
            for index, zone in enumerate(raw_zones):
                zone_id = str(zone.get("id") or f"zone_{index + 1}")
                zones[zone_id] = {
                    "id": zone_id,
                    "name": zone.get("name", zone_id.replace("_", " ").title()),
                    "lat": float(zone.get("lat", 0.0)),
                    "lon": float(zone.get("lon", 0.0)),
                    "base_load": float(zone.get("base_load_mw", self._base_load / max(len(raw_zones), 1))),
                    "renewable_share": float(zone.get("renewable_share", cfg.get("renewable_share", 0.4))),
                    "residential_share": float(zone.get("residential_share", 0.4)),
                    "commercial_share": float(zone.get("commercial_share", 0.25)),
                    "industrial_share": float(zone.get("industrial_share", 0.2)),
                    "transport_weight": float(zone.get("transport_weight", 1.0)),
                    "carbon_factor": float(zone.get("carbon_factor", 0.32)),
                    "tariff_wholesale": float(zone.get("tariff_wholesale", self._pricing_cfg.get("wholesale_tariff", self._base_price))),
                    "retail_markup": float(zone.get("retail_markup", self._pricing_cfg.get("retail_markup", 0.15))),
                    "comfort_temp_c": float(zone.get("comfort_temp_c", 22.0)),
                    "cooling_coefficient": float(zone.get("cooling_coefficient", 0.01)),
                    "heating_coefficient": float(zone.get("heating_coefficient", 0.01)),
                    "foot_traffic_weight": float(zone.get("foot_traffic_weight", 1.0)),
                }
        else:
            total = int(cfg.get("zones", 4))
            for index in range(total):
                zone_id = f"zone_{index + 1}"
                zones[zone_id] = {
                    "id": zone_id,
                    "name": zone_id.replace("_", " ").title(),
                    "lat": 40.70 + index * 0.03,
                    "lon": -73.99 + index * 0.04,
                    "base_load": self._base_load / max(total, 1),
                    "renewable_share": cfg.get("renewable_share", 0.4),
                    "residential_share": 0.4,
                    "commercial_share": 0.25,
                    "industrial_share": 0.2,
                    "transport_weight": 1.0,
                    "carbon_factor": 0.32,
                    "tariff_wholesale": self._pricing_cfg.get("wholesale_tariff", self._base_price),
                    "retail_markup": self._pricing_cfg.get("retail_markup", 0.15),
                    "comfort_temp_c": 22.0,
                    "cooling_coefficient": 0.01,
                    "heating_coefficient": 0.01,
                    "foot_traffic_weight": 1.0,
                }
        total_weight = sum(zone["transport_weight"] for zone in zones.values()) or 1.0
        for zone in zones.values():
            zone["transport_weight"] /= total_weight
        return zones

    def _load_lines(self, cfg: dict[str, Any], zones: Dict[str, dict[str, Any]]) -> List[TransmissionLine]:
        raw_lines = cfg.get("transmission_lines", [])
        lines: List[TransmissionLine] = []
        if isinstance(raw_lines, list) and raw_lines:
            for index, line in enumerate(raw_lines):
                origin = str(line.get("from"))
                destination = str(line.get("to"))
                if origin not in zones or destination not in zones:
                    continue
                identifier = str(line.get("id") or f"line_{index + 1}")
                capacity = float(line.get("capacity_mw", 90.0))
                loss_pct = float(line.get("loss_pct", 3.5))
                lines.append(TransmissionLine(identifier, origin, destination, capacity, loss_pct))
        else:
            zone_ids = list(zones.keys())
            for index in range(len(zone_ids)):
                origin = zone_ids[index]
                destination = zone_ids[(index + 1) % len(zone_ids)]
                identifier = f"ring_{index + 1}"
                lines.append(TransmissionLine(identifier, origin, destination, 85.0, 3.5))
        return lines

    def _build_adjacency(self) -> Dict[str, List[str]]:
        adjacency: Dict[str, List[str]] = {zone: [] for zone in self._zones}
        for line in self._lines:
            adjacency[line.origin].append(line.destination)
            adjacency[line.destination].append(line.origin)
        return adjacency

    # ------------------------------------------------------------------
    # Simulation hooks
    # ------------------------------------------------------------------
    def on_start(self) -> None:
        logger.info("Energy subsystem initialised with %d zones and %d lines", len(self._zones), len(self._lines))

    def execute_tick(self) -> None:
        base_scalar = float(self.get_control("energy_base_load", 1.0))
        base_scalar = max(0.2, min(base_scalar, 3.0))

        renewable_boost = float(self.get_control("renewable_boost", 0.0))
        renewable_boost = max(0.0, min(renewable_boost, 1.0))
        
        # Street lighting load (scenario parameter)
        street_lighting = float(self.get_control("street_lighting_load", 0.0))
        power_lines_down = int(self.get_control("power_lines_down", 0))

        # Calculate transport energy directly from traffic vehicles (simplified)
        traffic_vehicles = float(self.get_metric("traffic", "vehicles", 0.0))
        waste_route_km = float(self.get_metric("waste", "avg_route_km", 0.0))
        # Simplified transport energy calculation
        traffic_ev = max(0.0, traffic_vehicles * 0.02)  # Simplified EV demand
        waste_energy = max(0.0, waste_route_km * 0.015)  # Simplified fleet energy
        emergency_energy = float(self.get_metric("emergency", "grid_demand_mwh", 0.0))

        transport_energy = traffic_ev + waste_energy
        critical_energy = emergency_energy * 1.15

        industrial_scalar = 0.92 + self._rng.uniform(-0.04, 0.1)
        tick = 0
        try:
            tick = self.kernel.current_tick()
        except Exception:
            pass
        weather = self._weather.snapshot(tick)
        temperature = weather["temperature_c"]
        foot_traffic_index = weather["foot_traffic_index"]
        solar_index = weather["solar_index"]
        weather_effects = weather.get("weather_effects", {})
        wind_multiplier = weather.get("wind_multiplier", 1.0)

        zone_runtime: Dict[str, dict[str, float]] = {}
        total_consumption = 0.0
        total_generation = 0.0
        total_renewables = 0.0

        for zone_id, zone in self._zones.items():
            noise = self._rng.uniform(0.96, 1.08)
            base_load = zone["base_load"] * base_scalar * noise

            temp_delta = temperature - zone["comfort_temp_c"]
            temp_factor = 1.0
            if temp_delta >= 0:
                temp_factor += temp_delta * zone["cooling_coefficient"]
            else:
                temp_factor += abs(temp_delta) * zone["heating_coefficient"]

            residential = base_load * zone["residential_share"] * temp_factor
            commercial = base_load * zone["commercial_share"] * (1.0 + self._rng.uniform(-0.04, 0.05))
            industrial = base_load * zone["industrial_share"] * industrial_scalar
            mobility = transport_energy * zone["transport_weight"] * (1.0 + 0.12 * foot_traffic_index)
            critical = critical_energy / max(len(self._zones), 1)
            lighting = street_lighting / max(len(self._zones), 1)  # Distribute street lighting across zones

            consumption = residential + commercial + industrial + mobility + critical + lighting

            # Apply weather effects to renewable generation
            renewable_multiplier = weather_effects.get("renewable", 1.0)
            # Solar generation affected by solar_index and weather
            solar_generation = (0.6 + 0.4 * solar_index) * weather_effects.get("solar", 1.0)
            # Wind generation (assume 40% of renewable is wind-based)
            wind_generation = 0.4 * wind_multiplier * weather_effects.get("wind", 1.0)
            # Combined renewable multiplier
            effective_renewable_mult = renewable_multiplier * (0.6 * solar_generation + 0.4 * wind_generation)
            
            renewable_potential = (
                base_load
                * (zone["renewable_share"] + renewable_boost * 0.5)
                * effective_renewable_mult
            )
            renewable_output = max(0.0, renewable_potential + self._rng.uniform(-3.0, 4.0))
            dispatchable = max(consumption - renewable_output + 10.0, 6.0)
            generation = renewable_output + dispatchable
            surplus = generation - consumption

            weather_penalty = abs(temp_delta) * self._local_costs.get("temperature_penalty", 4.0)
            foot_penalty = foot_traffic_index * zone["foot_traffic_weight"] * self._local_costs.get("foot_traffic_penalty", 6.0)
            local_cost_index = weather_penalty + foot_penalty

            zone_runtime[zone_id] = {
                "residential": residential,
                "commercial": commercial,
                "industrial": industrial,
                "mobility": mobility,
                "critical": critical,
                "consumption": consumption,
                "generation": generation,
                "renewable_output": renewable_output,
                "dispatchable": dispatchable,
                "surplus": surplus,
                "local_cost_index": local_cost_index,
            }

            total_consumption += consumption
            total_generation += generation
            total_renewables += renewable_output

        # Apply power lines down scenario (disable some transmission lines)
        active_lines = self._lines
        if power_lines_down > 0:
            # Disable the first N lines
            active_lines = self._lines[:-power_lines_down] if power_lines_down < len(self._lines) else []
        
        # Rebuild adjacency if lines changed
        if power_lines_down > 0 and active_lines != self._lines:
            old_adjacency = self._adjacency
            self._adjacency = self._build_adjacency_from_lines(active_lines)
        
        line_metrics, transmission_losses = self._balance_power(zone_runtime, active_lines)
        total_losses = transmission_losses

        storage_delta = 0.0
        total_unserved = 0.0
        storage_dispatched = 0.0

        # Use storage to cover remaining deficits
        available_storage = self._storage_level
        for zone_id, state in zone_runtime.items():
            deficit = max(-state["surplus"], 0.0)
            if deficit and available_storage > 0:
                restored = min(deficit, available_storage)
                state["surplus"] += restored
                available_storage -= restored
                storage_delta -= restored
                storage_dispatched += restored
        self._storage_level += storage_delta

        # Store remaining surplus in storage
        remaining_surplus = sum(max(state["surplus"], 0.0) for state in zone_runtime.values())
        if remaining_surplus > 0:
            available_capacity = self._storage_capacity - self._storage_level
            stored = min(remaining_surplus, available_capacity)
            carry = stored
            if stored > 0:
                for state in zone_runtime.values():
                    if carry <= 0:
                        break
                    surplus = max(state["surplus"], 0.0)
                    if surplus <= 0:
                        continue
                    take = min(surplus, carry)
                    state["surplus"] -= take
                    carry -= take
                self._storage_level += stored
            self._storage_input_cumulative += max(stored, 0.0)
        self._storage_output_cumulative += max(storage_dispatched, 0.0)

        # Compute post-storage deficits
        for zone_id, state in zone_runtime.items():
            deficit = max(-state["surplus"], 0.0)
            total_unserved += deficit
            state["unserved"] = deficit
            state["delivered"] = state["consumption"] - deficit
            state["carbon_intensity"] = self._compute_carbon_intensity(state)
            wholesale, retail = self._compute_price(zone_id, state, line_metrics)
            state["price_wholesale"] = wholesale
            state["price_retail"] = retail
            state["net_import_mw"] = max(-state["surplus"], 0.0)

        blackout_risk = min(1.0, total_unserved / max(total_consumption, 1.0) * 4.0)
        renewable_ratio = total_renewables / max(total_generation, 1.0)
        total_losses += sum(state["unserved"] for state in zone_runtime.values())
        self._grid_losses = total_losses

        utilisation_ratio = total_consumption / max(total_generation, 1.0)
        self._demand_response_active = utilisation_ratio > 0.95 or blackout_risk > 0.2

        avg_price = sum(state["price_retail"] for state in zone_runtime.values()) / max(len(zone_runtime), 1)
        price_index = avg_price / self._base_price

        transmission_efficiency = (total_consumption - total_unserved) / max(total_generation, 1.0)
        transmission_efficiency = max(0.0, min(transmission_efficiency, 1.0))
        storage_eff = self._storage_output_cumulative / self._storage_input_cumulative

        self._record_history("transmission_efficiency", transmission_efficiency)
        self._record_history("renewable_ratio", renewable_ratio)
        self._record_history("storage_efficiency", storage_eff)
        self._record_history("avg_price", avg_price)
        avg_carbon = sum(state["carbon_intensity"] for state in zone_runtime.values()) / max(len(zone_runtime), 1)
        self._record_history("carbon_intensity", avg_carbon)

        demand_response_cost = 0.0
        if self._demand_response_active:
            excess = max(0.0, utilisation_ratio - 0.95)
            demand_response_cost = excess * total_consumption * self._local_costs.get("demand_response_cost_per_mwh", 18.0)
        optimization_costs = {
            "demand_response_cost": round(demand_response_cost, 2),
            "weather_penalty": round(abs(temperature - 22.0) * self._local_costs.get("temperature_penalty", 4.0), 2),
            "mobility_penalty": round(foot_traffic_index * self._local_costs.get("foot_traffic_penalty", 6.0), 2),
        }

        # Simplified metrics - removed noise: losses_mw, blackout_risk, lines_congested, 
        # avg_price_mwh (kept price_index), transmission_efficiency (kept in KPIs only)
        # Merged lines_congested into transmission_efficiency concept
        grid_efficiency = transmission_efficiency * (1.0 - min(sum(1 for line in line_metrics if line["utilization"] >= 0.85) / max(len(line_metrics), 1), 0.2))
        
        self._latest_metrics = {
            "generation_mw": round(total_generation, 2),
            "consumption_mw": round(total_consumption, 2),
            "surplus_mw": round(total_generation - total_consumption, 2),
            "renewable_ratio": round(renewable_ratio, 3),
            "storage_mwh": round(self._storage_level, 2),
            "price_index": round(price_index, 3),
            "carbon_intensity": round(avg_carbon, 3),
            "zones": self._format_zone_snapshot(zone_runtime),
            "lines": line_metrics,
            "weather": weather,  # Includes weather_condition and weather_effects
            "kpis": {
                "transmission_efficiency": round(transmission_efficiency, 3),
                "renewable_utilization": round(renewable_ratio, 3),
                "storage_round_trip_efficiency": round(storage_eff, 3),
                "avg_price_mwh": round(avg_price, 2),
                "avg_carbon_intensity": round(avg_carbon, 3),
            },
            "kpi_trend": {
                key: round(sum(values) / len(values), 3) if values else 0.0
                for key, values in self._history.items()
            },
            "optimization_costs": optimization_costs,
        }

        logger.debug(
            (
                "Energy tick: gen=%.1fMW load=%.1fMW renewable=%.1fMW storage=%.1fMWh "
                "price_index=%.2f losses=%.1fMW blackout=%.2f temp=%.1fC"
            ),
            total_generation,
            total_consumption,
            total_renewables,
            self._storage_level,
            price_index,
            total_losses,
            blackout_risk,
            temperature,
        )

    def collect_metrics(self) -> dict[str, Any]:
        return dict(self._latest_metrics)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_adjacency_from_lines(self, lines: List[TransmissionLine]) -> Dict[str, List[str]]:
        """Rebuild adjacency matrix from a subset of lines."""
        adjacency: Dict[str, List[str]] = {zone: [] for zone in self._zones}
        for line in lines:
            adjacency[line.origin].append(line.destination)
            adjacency[line.destination].append(line.origin)
        return adjacency

    def _balance_power(self, zone_runtime: Dict[str, dict[str, float]], lines: List[TransmissionLine] | None = None) -> tuple[list[dict[str, Any]], float]:
        if lines is None:
            lines = self._lines
        zone_surplus = {zone_id: state["surplus"] for zone_id, state in zone_runtime.items()}
        line_flow: Dict[str, float] = {line.identifier: 0.0 for line in lines}
        line_losses: Dict[str, float] = {line.identifier: 0.0 for line in lines}

        for _ in range(2):
            for line in lines:
                origin_surplus = zone_surplus[line.origin]
                dest_surplus = zone_surplus[line.destination]
                source_id: str | None = None
                dest_id: str | None = None

                if origin_surplus > 0 and dest_surplus < 0:
                    source_id, dest_id = line.origin, line.destination
                elif dest_surplus > 0 and origin_surplus < 0:
                    source_id, dest_id = line.destination, line.origin

                if source_id is None or dest_id is None:
                    continue

                available = min(zone_surplus[source_id], abs(zone_surplus[dest_id]), line.capacity_mw)
                if available <= 0:
                    continue

                loss = available * (line.loss_pct / 100.0)
                zone_surplus[source_id] -= available
                zone_surplus[dest_id] += available - loss

                sign = 1 if source_id == line.origin else -1
                line_flow[line.identifier] += sign * available
                line_losses[line.identifier] += loss

        for zone_id, surplus in zone_surplus.items():
            zone_runtime[zone_id]["surplus"] = surplus

        line_metrics: list[dict[str, Any]] = []
        for line in lines:
            flow = line_flow.get(line.identifier, 0.0)
            utilization = min(1.0, abs(flow) / max(line.capacity_mw, 1.0))
            start = self._zones[line.origin]
            end = self._zones[line.destination]
            line_metrics.append(
                {
                    "id": line.identifier,
                    "from": line.origin,
                    "to": line.destination,
                    "flow_mw": round(flow, 2),
                    "capacity_mw": line.capacity_mw,
                    "utilization": round(utilization, 3),
                    "loss_mw": round(line_losses.get(line.identifier, 0.0), 2),
                    "from_lat": start["lat"],
                    "from_lon": start["lon"],
                    "to_lat": end["lat"],
                    "to_lon": end["lon"],
                }
            )

        total_losses = sum(line_losses.values())
        return line_metrics, total_losses

    def _compute_price(self, zone_id: str, state: dict[str, float], lines: Iterable[dict[str, Any]]) -> tuple[float, float]:
        congestion = 0.0
        touching = 0
        for line in lines:
            if line["from"] == zone_id or line["to"] == zone_id:
                congestion += line["utilization"]
                touching += 1
        congestion_factor = congestion / touching if touching else 0.0
        scarcity = state.get("unserved", 0.0) / max(state["consumption"], 1.0)
        zone_cfg = self._zones[zone_id]
        base_tariff = zone_cfg.get("tariff_wholesale", self._pricing_cfg.get("wholesale_tariff", self._base_price))
        carbon_price = self._pricing_cfg.get("carbon_price_per_ton", 35.0)
        carbon_cost = state["carbon_intensity"] * carbon_price
        delivery_cost = self._pricing_cfg.get("transmission_cost_per_mw", 0.8) * (1.0 + congestion_factor)
        congestion_surcharge = congestion_factor * 10.0
        scarcity_surcharge = scarcity * 28.0
        wholesale = base_tariff + carbon_cost + delivery_cost + congestion_surcharge + scarcity_surcharge
        retail = wholesale * (1.0 + zone_cfg.get("retail_markup", self._pricing_cfg.get("retail_markup", 0.18)))
        return round(wholesale, 2), round(retail, 2)

    def _compute_carbon_intensity(self, state: dict[str, float]) -> float:
        thermal = state["dispatchable"]
        delivered = max(state["delivered"], 1.0)
        return min(1.5, thermal * 0.4 / delivered)

    def _format_zone_snapshot(self, zone_runtime: Dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        snapshot: list[dict[str, Any]] = []
        for zone_id, zone in self._zones.items():
            runtime = zone_runtime[zone_id]
            snapshot.append(
                {
                    "id": zone_id,
                    "name": zone["name"],
                    "lat": zone["lat"],
                    "lon": zone["lon"],
                    "load_mw": round(runtime["consumption"], 2),
                    "generation_mw": round(runtime["generation"], 2),
                    "delivered_mw": round(runtime["delivered"], 2),
                    "unserved_mw": round(runtime["unserved"], 2),
                    "price_wholesale": runtime["price_wholesale"],
                    "price_retail": runtime["price_retail"],
                    "surplus_mw": round(runtime["surplus"], 2),
                    "renewable_ratio": round(runtime["renewable_output"] / max(runtime["generation"], 1.0), 3),
                    "carbon_intensity": round(runtime["carbon_intensity"], 3),
                    "local_cost_index": round(runtime["local_cost_index"], 2),
                    "net_import_mw": round(runtime["net_import_mw"], 2),
                }
            )
        return snapshot

    def _record_history(self, key: str, value: float) -> None:
        series = self._history.get(key)
        if series is not None:
            series.append(value)

