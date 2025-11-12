"""Abstract base implementation for subsystem worker threads."""

from __future__ import annotations

import logging
import threading
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.context import CityContext
    from src.core.kernel import CityKernel

logger = logging.getLogger(__name__)


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

        try:
            self.on_start()
            while not self._shutdown.is_set() and self._wait_for_tick():
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
        self._kernel.publish_metrics(self.identifier, metrics)

    def get_metric(self, subsystem: str, key: str, default: Any = 0) -> Any:
        """Convenience accessor for latest metrics from another subsystem."""

        latest = self.context.get_latest(subsystem)
        if latest is None:
            return default
        _, metrics = latest
        return metrics.get(key, default)

    @property
    def identifier(self) -> str:
        return self._identifier

    def set_identifier(self, identifier: str) -> None:
        self._identifier = identifier

