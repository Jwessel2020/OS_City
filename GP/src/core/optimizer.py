"""Optimization engine for configuring and maintaining local efficiency optimums."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OptimizationGoal:
    metric_path: str  # e.g. "traffic.congestion_index"
    target_value: float
    weight: float = 1.0
    tolerance: float = 0.05
    minimize: bool = True  # True = target is 0 or lower, False = target is high

@dataclass
class ControlKnob:
    control_key: str  # e.g. "traffic_signal_bias"
    min_value: float
    max_value: float
    current_value: float
    step_size: float = 0.1


class CityOptimizer:
    """
    Feedback loop controller that adjusts system controls to approach defined optimums.
    Uses a simplified gradient descent / hill climbing approach.
    """

    def __init__(self, context: Any) -> None:
        self._context = context
        self._goals: Dict[str, OptimizationGoal] = {}
        self._knobs: Dict[str, ControlKnob] = {}
        self._active = False
        self._lock = threading.RLock()
        self._history: List[float] = []

    def add_goal(self, name: str, goal: OptimizationGoal) -> None:
        with self._lock:
            self._goals[name] = goal

    def add_knob(self, knob: ControlKnob) -> None:
        with self._lock:
            self._knobs[knob.control_key] = knob
            # Sync initial value to context
            self._context.update_controls({knob.control_key: knob.current_value})

    def toggle(self, active: bool) -> None:
        self._active = active
        logger.info("Optimizer state changed to: %s", "ACTIVE" if active else "IDLE")

    def step(self) -> None:
        """Execute one optimization step."""
        if not self._active:
            return

        with self._lock:
            # 1. Calculate total error/score
            total_error = 0.0
            goal_errors = {}

            for name, goal in self._goals.items():
                # Parse metric path "subsystem.key"
                parts = goal.metric_path.split(".")
                if len(parts) != 2:
                    continue
                
                subsystem, key = parts
                latest = self._context.get_latest(subsystem)
                if not latest:
                    continue
                
                _, metrics = latest
                current_val = float(metrics.get(key, 0.0))
                
                # Normalize error
                if goal.minimize:
                    # For minimization, we want current_val <= target_value
                    # Error is positive if current_val > target_value
                    error = max(0.0, current_val - goal.target_value)
                else:
                    # For maximization, we want current_val >= target_value
                    # Error is positive if current_val < target_value
                    error = max(0.0, goal.target_value - current_val)
                
                weighted_error = error * goal.weight
                total_error += weighted_error
                goal_errors[name] = weighted_error

            self._history.append(total_error)
            if len(self._history) > 100:
                self._history.pop(0)

            # 2. Adjust knobs
            # This is a naive implementation: it randomly perturbs knobs and checks if it helps.
            # For a "True Virtual Twin", we might want a PID or model-based approach, 
            # but random search is robust for complex chaotic systems like this.
            
            # Actually, let's use a simple heuristic rule-based approach for demo purposes
            # because random search needs rollback/simulation capabilities we don't have in real-time.
            
            self._apply_heuristics(goal_errors)

    def _apply_heuristics(self, errors: Dict[str, float]) -> None:
        """Apply domain-specific heuristics to adjust knobs based on errors."""
        updates = {}

        # Heuristic 1: High Traffic Congestion -> Increase Signal Bias, Increase Road Pricing (reduce inflow)
        traffic_error = errors.get("minimize_congestion", 0.0)
        if traffic_error > 0.1:
            self._adjust_knob("traffic_signal_bias", 1, updates) # Increase efficiency bias
            self._adjust_knob("traffic_inflow", -1, updates)     # Reduce inflow

        # Heuristic 2: High Energy Price -> Reduce Demand (Demand Response), Increase Renewable Boost
        energy_error = errors.get("minimize_energy_price", 0.0)
        if energy_error > 0.1:
            self._adjust_knob("energy_base_load", -1, updates)   # Reduce demand
            self._adjust_knob("renewable_boost", 1, updates)     # More renewables

        # Heuristic 3: High Waste Backlog -> Increase Fleet
        waste_error = errors.get("minimize_waste_backlog", 0.0)
        if waste_error > 0.1:
            self._adjust_knob("waste_fleet_size", 1, updates)

        # Heuristic 4: High Incidents -> Increase Emergency Staff
        emergency_error = errors.get("minimize_incidents", 0.0)
        if emergency_error > 0.1:
            self._adjust_knob("emergency_staff", 1, updates)
            self._adjust_knob("traffic_signal_bias", 1, updates) # Try to clear traffic for emergency vehicles

        if updates:
            self._context.update_controls(updates)
            # logger.debug("Optimizer adjusted controls: %s", updates)

    def _adjust_knob(self, key: str, direction: int, updates: Dict[str, Any]) -> None:
        knob = self._knobs.get(key)
        if not knob:
            return
        
        delta = knob.step_size * direction
        new_val = max(knob.min_value, min(knob.max_value, knob.current_value + delta))
        
        if new_val != knob.current_value:
            knob.current_value = new_val
            updates[key] = new_val

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "goals": [
                    {
                        "name": name,
                        "target": g.target_value,
                        "current_error": self._get_current_error(g)
                    }
                    for name, g in self._goals.items()
                ],
                "knobs": {k: v.current_value for k, v in self._knobs.items()},
                "global_error": self._history[-1] if self._history else 0.0
            }

    def _get_current_error(self, goal: OptimizationGoal) -> float:
        parts = goal.metric_path.split(".")
        if len(parts) != 2: return 0.0
        subsystem, key = parts
        latest = self._context.get_latest(subsystem)
        if not latest: return 0.0
        val = float(latest[1].get(key, 0.0))
        if goal.minimize:
            return max(0.0, val - goal.target_value)
        return max(0.0, goal.target_value - val)

