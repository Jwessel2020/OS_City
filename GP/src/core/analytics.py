"""Analytical engine for calculating deep insights and correlations."""

from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CityAnalytics:
    """
    Process historical data to find correlations and trends.
    """

    def __init__(self, context: Any, window_size: int = 100) -> None:
        self._context = context
        self._window_size = window_size
        # Stores time-series data: { "subsystem.metric": [v1, v2, ...] }
        self._timeseries: Dict[str, deque] = {}
        self._correlations: Dict[str, float] = {}

    def track(self, subsystem: str, metrics: Dict[str, Any]) -> None:
        """Ingest a new data point."""
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                full_key = f"{subsystem}.{key}"
                if full_key not in self._timeseries:
                    self._timeseries[full_key] = deque(maxlen=self._window_size)
                self._timeseries[full_key].append(value)

    def analyze(self) -> None:
        """Perform heavy analytical computations (correlations)."""
        # Define key pairs to check for correlations
        pairs = [
            ("traffic.congestion_index", "energy.price_index"),
            ("traffic.congestion_index", "waste.pending_requests"),
            ("traffic.congestion_index", "emergency.avg_response_min"),
            ("energy.price_index", "waste.avg_route_km"),
            ("traffic.vehicles", "traffic.incidents"),
            ("energy.renewable_ratio", "energy.price_index"),
            ("traffic.avg_speed_kmh", "traffic.emissions_co2"),
        ]

        results = {}
        for key_a, key_b in pairs:
            series_a = self._timeseries.get(key_a)
            series_b = self._timeseries.get(key_b)

            if series_a and series_b and len(series_a) > 10 and len(series_a) == len(series_b):
                corr = self._pearson_correlation(list(series_a), list(series_b))
                results[f"{key_a}|{key_b}"] = corr

        self._correlations = results

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        n = len(x)
        if n != len(y): return 0.0
        
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_sq_x = sum(xi ** 2 for xi in x)
        sum_sq_y = sum(yi ** 2 for yi in y)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_sq_x - sum_x ** 2) * (n * sum_sq_y - sum_y ** 2))

        if denominator == 0:
            return 0.0
        
        return numerator / denominator

    def get_insights(self) -> Dict[str, Any]:
        narratives = self._generate_narratives()
        return {
            "correlations": self._correlations,
            "trends": self._calculate_trends(),
            "narratives": narratives
        }

    def _calculate_trends(self) -> Dict[str, str]:
        """Simple linear regression slope to determine trend direction."""
        trends = {}
        for key, series in self._timeseries.items():
            if len(series) < 10:
                continue
            
            # Take last 10 points
            subset = list(series)[-10:]
            start = subset[0]
            end = subset[-1]
            
            if start == 0: 
                change = 0.0
            else:
                change = (end - start) / abs(start)

            if change > 0.05:
                trends[key] = "rising"
            elif change < -0.05:
                trends[key] = "falling"
            else:
                trends[key] = "stable"
        return trends

    def _generate_narratives(self) -> List[str]:
        """Translate strong correlations into natural language insights."""
        narratives = []
        
        # Mapping nice names
        names = {
            "traffic.congestion_index": "Traffic Congestion",
            "energy.price_index": "Energy Prices",
            "waste.pending_requests": "Waste Backlog",
            "emergency.avg_response_min": "Emergency Response Time",
            "energy.renewable_ratio": "Renewable Energy Mix",
            "traffic.vehicles": "Vehicle Volume",
            "traffic.incidents": "Traffic Incidents",
            "traffic.emissions_co2": "CO2 Emissions",
            "traffic.avg_speed_kmh": "Average Traffic Speed"
        }

        for pair, corr in self._correlations.items():
            if abs(corr) < 0.4:
                continue
            
            key_a, key_b = pair.split("|")
            name_a = names.get(key_a, key_a)
            name_b = names.get(key_b, key_b)
            
            if corr > 0.7:
                narratives.append(f"⚠️ High {name_a} is strongly driving up {name_b} (corr: {corr:.2f})")
            elif corr > 0.4:
                narratives.append(f"ℹ️ {name_a} tends to increase {name_b} (corr: {corr:.2f})")
            elif corr < -0.7:
                narratives.append(f"✅ Increasing {name_a} strongly reduces {name_b} (corr: {corr:.2f})")
            elif corr < -0.4:
                narratives.append(f"ℹ️ {name_a} tends to lower {name_b} (corr: {corr:.2f})")
        
        # Sort by strength
        narratives.sort(key=lambda s: abs(float(s.split("corr: ")[1][:-1])), reverse=True)
        return narratives[:5]  # Top 5 insights
