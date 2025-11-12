"""High-level controller for managing the simulation kernel lifecycle."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.core.kernel import CityKernel

logger = logging.getLogger(__name__)


@dataclass
class ControlState:
    """Mutable simulation controls shared across subsystems."""

    traffic_inflow: float = 1.0
    energy_base_load: float = 1.0
    waste_request_rate: float = 1.0
    emergency_override: bool = False
    paused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "traffic_inflow": self.traffic_inflow,
            "energy_base_load": self.energy_base_load,
            "waste_request_rate": self.waste_request_rate,
            "emergency_override": self.emergency_override,
            "paused": self.paused,
        }


class SimulationController:
    """Manage kernel execution and expose control hooks for the UI."""

    def __init__(self, kernel: CityKernel) -> None:
        self.kernel = kernel
        self.controls = ControlState()
        self._thread: Optional[threading.Thread] = None
        self._metrics_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._on_state_change: list[Callable[[ControlState], None]] = []
        self._history_lock = threading.Lock()
        self._history: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        self._history_limit = 300

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.debug("Simulation already running")
                return

            self.kernel.reset()
            self.kernel.set_control_state(self.controls.to_dict())
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_kernel_loop,
                name="SimulationControllerThread",
                daemon=True,
            )
            self._thread.start()

            self._metrics_thread = threading.Thread(
                target=self._consume_metrics,
                name="MetricsAggregatorThread",
                daemon=True,
            )
            self._metrics_thread.start()

    def _run_kernel_loop(self) -> None:
        try:
            self.kernel.run()
        except Exception:
            logger.exception("Kernel encountered an unrecoverable error")
            raise
        finally:
            self._stop_event.set()

    def pause(self) -> None:
        self.set_control("paused", True)

    def resume(self) -> None:
        self.set_control("paused", False)

    def toggle_pause(self) -> None:
        self.set_control("paused", not self.controls.paused)

    def reset(self) -> None:
        with self._lock:
            self._stop_event.set()
            self.kernel.shutdown()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3)
            if self._metrics_thread and self._metrics_thread.is_alive():
                self._metrics_thread.join(timeout=3)
            self.controls = ControlState()
            self.kernel.reset()
            with self._history_lock:
                self._history.clear()
            self.kernel.set_control_state(self.controls.to_dict())

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self.kernel.shutdown()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3)
            if self._metrics_thread and self._metrics_thread.is_alive():
                self._metrics_thread.join(timeout=3)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    def set_control(self, key: str, value: Any) -> None:
        if not hasattr(self.controls, key):
            raise AttributeError(f"Unknown control: {key}")
        setattr(self.controls, key, value)
        self.kernel.set_control_state(self.controls.to_dict())
        for callback in self._on_state_change:
            callback(self.controls)

    def register_control_listener(self, callback: Callable[[ControlState], None]) -> None:
        self._on_state_change.append(callback)

    def trigger_emergency(self, duration: float = 5.0) -> None:
        self.set_control("emergency_override", True)

        def _clear() -> None:
            try:
                self.set_control("emergency_override", False)
            except Exception:
                logger.debug("Failed to clear emergency override", exc_info=True)

        timer = threading.Timer(duration, _clear)
        timer.daemon = True
        timer.start()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def is_running(self) -> bool:
        return self.kernel.is_running() and not self._stop_event.is_set()

    def wait_until_stopped(self, timeout: float | None = None) -> bool:
        return self._stop_event.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # Metrics history
    # ------------------------------------------------------------------
    def _consume_metrics(self) -> None:
        while not self._stop_event.is_set():
            event = self.kernel.metrics_stream(timeout=0.5)
            if not event:
                continue
            event_type = event.get("type")
            if event_type == "shutdown":
                break
            if event_type != "metrics":
                continue

            subsystem = str(event.get("subsystem", ""))
            tick = int(event.get("tick", 0))
            metrics = event.get("metrics", {})

            with self._history_lock:
                bucket = self._history.setdefault(subsystem, [])
                bucket.append((tick, metrics))
                if len(bucket) > self._history_limit:
                    del bucket[0 : len(bucket) - self._history_limit]

    def get_history(self) -> dict[str, list[tuple[int, dict[str, Any]]]]:
        with self._history_lock:
            return {sub: list(entries) for sub, entries in self._history.items()}

