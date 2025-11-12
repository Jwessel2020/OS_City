"""City-wide simulation kernel orchestrating subsystem threads."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from queue import Empty, Queue
from typing import Any, Optional

from src.core.context import CityContext
from src.subsystems.base import SubsystemThread
from src.subsystems.factory import build_subsystems_from_config

logger = logging.getLogger(__name__)


class CityKernel:
    """Coordinates lifecycle and synchronization of subsystem threads."""

    def __init__(
        self,
        config: dict[str, Any],
        tick_duration: float = 0.5,
        max_ticks: int | None = None,
    ) -> None:
        self.config = config
        self.tick_duration = tick_duration
        self.max_ticks = max_ticks

        self._subsystems: list[SubsystemThread] = []
        self._running = threading.Event()
        self._tick_event = threading.Event()
        self._tick_barrier: threading.Barrier | None = None
        self._tick_index = 0
        self._lock = threading.Lock()
        self.context = CityContext()
        buffer_size = int(self.config.get("metrics_buffer", 256))
        self._metrics_queue: Queue[dict[str, Any]] = Queue(maxsize=buffer_size)
        self._latest_metrics: dict[str, dict[str, Any]] = {}
        self._pause_event = threading.Event()
        self._pause_event.set()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def bootstrap(self, force: bool = False) -> None:
        """Instantiate and prepare subsystem threads."""

        if force:
            self._subsystems = []
            self._tick_barrier = None

        if not self._subsystems:
            self._subsystems.extend(build_subsystems_from_config(self, self.config))

        if not self._subsystems:
            msg = "No subsystems registered for the simulation"
            raise RuntimeError(msg)

        self._tick_barrier = threading.Barrier(len(self._subsystems) + 1)

        for subsystem in self._subsystems:
            subsystem.attach_kernel(self)
            logger.debug("Registered subsystem: %s", subsystem.name)

    def register_subsystems(self, subsystems: Iterable[SubsystemThread]) -> None:
        """Add subsystems prior to bootstrapping."""

        if self._tick_barrier is not None:
            msg = "Cannot register subsystems after bootstrap"
            raise RuntimeError(msg)

        self._subsystems.extend(subsystems)

    def run(self) -> None:
        """Main simulation loop."""

        if self._tick_barrier is None:
            msg = "Kernel must be bootstrapped before running"
            raise RuntimeError(msg)

        self._running.set()

        for subsystem in self._subsystems:
            subsystem.start()
            logger.info("Started subsystem thread %s", subsystem.name)

        logger.info("Kernel entering main loop with %d subsystems", len(self._subsystems))

        try:
            while self._should_continue():
                tick_start = time.perf_counter()

                self._tick_event.set()
                try:
                    self._tick_barrier.wait()
                except threading.BrokenBarrierError:
                    logger.warning("Tick barrier broken; terminating loop")
                    break
                finally:
                    self._tick_event.clear()

                self._tick_index += 1

                self._pause_event.wait()

                elapsed = time.perf_counter() - tick_start
                sleep_time = max(self.tick_duration - elapsed, 0)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            self._running.clear()

    def shutdown(self) -> None:
        """Signal subsystems to stop and wait for their completion."""

        logger.debug("Initiating kernel shutdown")
        self._running.clear()

        if self._tick_barrier is not None:
            try:
                self._tick_barrier.abort()
            except threading.BrokenBarrierError:
                pass

        self._tick_event.set()

        for subsystem in self._subsystems:
            subsystem.shutdown()

        for subsystem in self._subsystems:
            if subsystem.ident is None:
                continue
            subsystem.join(timeout=2)
            if subsystem.is_alive():
                logger.warning("Subsystem %s did not terminate cleanly", subsystem.name)

        # Notify any listeners that the stream has ended
        try:
            self._metrics_queue.put_nowait({"type": "shutdown"})
        except Exception:  # queue may be full or closed
            pass

    def reset(self) -> None:
        """Reset internal state to allow a fresh run."""

        self._tick_index = 0
        self._metrics_queue = Queue(maxsize=self._metrics_queue.maxsize)
        self._latest_metrics.clear()
        self._pause_event.set()
        self.bootstrap(force=True)

    # ------------------------------------------------------------------
    # Synchronization helpers
    # ------------------------------------------------------------------
    def wait_for_tick(self) -> bool:
        """Block a subsystem thread until the kernel starts the next tick."""

        self._tick_event.wait()
        return self._running.is_set()

    def signal_tick_complete(self) -> None:
        """Notify the kernel that a subsystem completed the current tick."""

        if self._tick_barrier is None:
            return

        try:
            self._tick_barrier.wait()
        except threading.BrokenBarrierError:
            logger.debug("Barrier broken during tick completion")

    def current_tick(self) -> int:
        """Return the current tick index (0-based)."""

        with self._lock:
            return self._tick_index

    def is_running(self) -> bool:
        """Return True if the kernel main loop is active."""

        return self._running.is_set()

    # ------------------------------------------------------------------
    # Metrics and context
    # ------------------------------------------------------------------
    def publish_metrics(self, subsystem: str, metrics: dict[str, Any]) -> None:
        """Store metrics for a subsystem and push to the queue."""

        tick = self.current_tick()
        self.context.update(subsystem, tick, metrics)
        self._latest_metrics[subsystem] = dict(metrics)

        event = {
            "type": "metrics",
            "tick": tick,
            "subsystem": subsystem,
            "metrics": dict(metrics),
        }
        try:
            self._metrics_queue.put_nowait(event)
        except Exception:
            # Drop metrics if queue is saturated; warn once per subsystem
            logger.debug("Metrics queue is full; dropping event for %s", subsystem)

    def set_control_state(self, controls: dict[str, Any]) -> None:
        """Apply externally supplied control values."""

        paused = controls.get("paused")
        if isinstance(paused, bool):
            if paused:
                self._pause_event.clear()
            else:
                self._pause_event.set()

        self.context.update_controls(controls)

    def get_latest_metrics(self, subsystem: str | None = None) -> dict[str, Any]:
        """Return latest metrics for requested subsystem or all subsystems."""

        if subsystem is None:
            return dict(self._latest_metrics)
        return dict(self._latest_metrics.get(subsystem, {}))

    def metrics_stream(self, timeout: float | None = None) -> Optional[dict[str, Any]]:
        """Retrieve the next metrics event from the queue."""

        try:
            return self._metrics_queue.get(timeout=timeout)
        except Empty:
            return None

    def _should_continue(self) -> bool:
        if not self._running.is_set():
            return False
        if self.max_ticks is None:
            return True
        return self._tick_index < self.max_ticks

