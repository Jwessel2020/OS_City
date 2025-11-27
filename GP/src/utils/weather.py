"""Deterministic weather/foot-traffic generator for the simulation."""

from __future__ import annotations

import math
from typing import Any, Dict

# Weather effects on simulation systems
WEATHER_EFFECTS = {
    "Clear": {"traffic_speed": 1.0, "renewable": 1.0},
    "Rain": {"traffic_speed": 0.7, "solar": 0.3, "wind": 1.5},
    "Snow": {"traffic_speed": 0.4, "road_capacity": 0.6},
    "Windy": {"renewable": 1.8, "traffic_speed": 0.9},
}


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

    def _determine_weather_condition(self, temperature: float, humidity: float, tick: int) -> str:
        """Determine weather condition based on temperature, humidity, and time."""
        day_fraction = (tick % self._ticks_per_day) / max(self._ticks_per_day, 1)
        
        # Wind strength (simulated via day variation)
        wind_strength = abs(math.sin(day_fraction * math.tau * 2)) * 0.5
        
        # Snow: temperature < 0°C and high humidity
        if temperature < 0.0 and humidity > 0.7:
            return "Snow"
        
        # Rain: moderate temperature, high humidity
        if 5.0 < temperature < 25.0 and humidity > 0.75:
            return "Rain"
        
        # Windy: strong wind patterns
        if wind_strength > 0.4:
            return "Windy"
        
        # Default: Clear
        return "Clear"

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
        
        # Determine weather condition
        weather_condition = self._determine_weather_condition(temperature, humidity, tick)
        weather_effects = WEATHER_EFFECTS.get(weather_condition, WEATHER_EFFECTS["Clear"])
        
        # Apply weather effects to solar and wind
        solar_multiplier = weather_effects.get("solar", 1.0)
        wind_multiplier = weather_effects.get("wind", 1.0)
        solar_index = solar_index * solar_multiplier

        return {
            "temperature_c": round(temperature, 2),
            "humidity": round(humidity, 3),
            "foot_traffic_index": round(foot_traffic, 3),
            "solar_index": round(solar_index, 3),
            "weather_condition": weather_condition,
            "weather_effects": weather_effects,
            "wind_multiplier": wind_multiplier,
        }


