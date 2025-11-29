"""Abstract base implementation for subsystem worker threads."""

from __future__ import annotations

import logging
import threading
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.context import CityContext
    from src.core.kernel import CityKernel

from src.utils import trace

logger = logging.getLogger(__name__)
# trace = logging.getLogger("trace")


class SubsystemThread(threading.Thread):
    """Base class encapsulating shared subsystem thread behaviour."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, daemon=True)
        self._kernel: CityKernel | None = None
        self._config = config or {}
        self._shutdown = threading.Event()
        self._identifier = self._config.get("identifier", name.lower())

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def attach_kernel(self, kernel: CityKernel) -> None:
        """Provide the kernel context prior to thread start."""

        self._kernel = kernel

    def shutdown(self) -> None:
        """Signal the thread to exit gracefully."""

        self._shutdown.set()

    def run(self) -> None:  # noqa: D401
        """threading.Thread API entry point."""
        trace.log_event("THREAD", f"Thread '{self.name}' STARTED (TID: {threading.get_native_id()})")
        try:
            self.on_start()
            while not self._shutdown.is_set():
                trace.log_event("THREAD", f"Thread '{self.name}' WAITING for tick signal")
                if not self._wait_for_tick():
                    break
                
                trace.log_event("THREAD", f"Thread '{self.name}' RUNNING tick logic")
                self.before_tick()
                self.execute_tick()
                self.after_tick()
                
                snapshot = self.collect_metrics()
                if snapshot is not None:
                    self.publish_metrics(snapshot)
        except Exception:
            logger.exception("Subsystem %s encountered an unexpected error", self.name)
            raise
        finally:
            trace.log_event("THREAD", f"Thread '{self.name}' STOPPING")
            self.on_stop()

    # ------------------------------------------------------------------
    # Template methods for subclasses
    # ------------------------------------------------------------------
    def on_start(self) -> None:
        """Initialisation hook, executed once in thread context."""

    def before_tick(self) -> None:
        """Hook executed before each tick."""

    def execute_tick(self) -> None:
        """Perform work for the current tick; must be implemented."""

        raise NotImplementedError("SubsystemThread subclasses must implement execute_tick()")

    def after_tick(self) -> None:
        """Hook executed after each tick but before synchronisation."""

    def on_stop(self) -> None:
        """Cleanup hook executed when thread exits."""

    def collect_metrics(self) -> dict[str, Any] | None:
        """Return metrics snapshot for this tick."""

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def kernel(self) -> CityKernel:
        if self._kernel is None:
            raise RuntimeError("Kernel not attached")
        return self._kernel

    @property
    def context(self) -> CityContext:
        return self.kernel.context

    def _wait_for_tick(self) -> bool:
        if self._kernel is None:
            raise RuntimeError("Kernel not attached")

        continue_running = self._kernel.wait_for_tick()
        self._signal_tick_complete()
        return continue_running

    def _signal_tick_complete(self) -> None:
        if self._kernel is None:
            return
        self._kernel.signal_tick_complete()

    def publish_metrics(self, metrics: dict[str, Any]) -> None:
        if self._kernel is None:
            return
        # Trace data movement: Subsystem -> Kernel
        trace.log_event(
            "DATA FLOW",
            f"{self.identifier.upper()} -> KERNEL: Pushing metrics",
            payload=metrics
        )
        self._kernel.publish_metrics(self.identifier, metrics)

    def get_metric(self, subsystem: str, key: str, default: Any = 0) -> Any:
        """Convenience accessor for latest metrics from another subsystem."""

        latest = self.context.get_latest(subsystem)
        if latest is None:
            val = default
        else:
            _, metrics = latest
            val = metrics.get(key, default)
        
        # Trace data movement: Context -> Subsystem
        trace.log_event(
            "DATA FLOW",
            f"CONTEXT -> {self.identifier.upper()}: Read '{subsystem}.{key}'",
            payload=val
        )
        return val

    def get_control(self, key: str, default: Any = None) -> Any:
        val = self.context.get_control(key, default)
        # Trace data movement: Control -> Subsystem
        trace.log_event(
            "DATA FLOW",
            f"CONTROL -> {self.identifier.upper()}: Read knob '{key}'",
            payload=val
        )
        return val

    @property
    def identifier(self) -> str:
        return self._identifier

    def set_identifier(self, identifier: str) -> None:
        self._identifier = identifier

