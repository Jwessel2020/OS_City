"""Deterministic weather/foot-traffic generator for the simulation."""

from __future__ import annotations

import math
from typing import Any, Dict


class WeatherEngine:
    """Generates smooth weather and mobility signals based on tick index."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._base_temp = float(cfg.get("base_temp_c", 23.0))
        self._daily_variation = float(cfg.get("daily_variation", 6.0))
        self._seasonal_offset = float(cfg.get("seasonal_offset", 0.0))
        self._humidity_base = float(cfg.get("humidity_base", 0.55))
        self._foot_base = float(cfg.get("foot_traffic_base", 1.0))
        self._foot_temp_sensitivity = float(cfg.get("foot_traffic_temp_sensitivity", 0.02))
        self._ticks_per_day = int(cfg.get("ticks_per_day", 48))

    def snapshot(self, tick: int) -> Dict[str, float]:
        """Return current weather and mobility figures for the given tick."""

        day_fraction = (tick % self._ticks_per_day) / max(self._ticks_per_day, 1)
        seasonal = math.sin(tick / (self._ticks_per_day * 7) * math.tau) * self._seasonal_offset
        daily = math.sin(day_fraction * math.tau - math.pi / 2) * self._daily_variation
        temperature = self._base_temp + seasonal + daily

        humidity = max(0.2, min(0.95, self._humidity_base + 0.1 * math.sin(day_fraction * math.tau)))
        foot_traffic = self._foot_base * (1.0 + self._foot_temp_sensitivity * (temperature - 22.0))
        foot_traffic = max(0.4, min(1.8, foot_traffic))

        solar_index = max(0.0, math.sin(day_fraction * math.pi))

        return {
            "temperature_c": round(temperature, 2),
            "humidity": round(humidity, 3),
            "foot_traffic_index": round(foot_traffic, 3),
            "solar_index": round(solar_index, 3),
        }


