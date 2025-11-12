import threading
import time
from queue import Queue
import logging

logger = logging.getLogger(__name__)

class CityKernel:
    # Central loop that ticks subsystems in lock-step and aggregates metrics.
    def __init__(self, subsystems, tick_duration=0.5):
        self.subsystems = subsystems
        self.tick_duration = tick_duration

        # Barrier includes +1 for the kernel itself
        self._barrier = threading.Barrier(len(subsystems) + 1)
        self._running = threading.Event()
        self.metrics_stream = Queue()

    def run(self, max_ticks=50):
        # Start all subsystem threads and iterate for a fixed number of ticks.
        self._running.set()
        for subsystem in self.subsystems:
            logger.debug("Starting subsystem thread %s", subsystem.name)
            subsystem.start()

        for tick in range(max_ticks):
            if not self._running.is_set():
                break
            logger.debug("Tick %s starting", tick)

            # Phase 1: release subsystems so they can do work
            logger.debug("Kernel releasing subsystems at tick %s", tick)
            self._barrier.wait()

            # Phase 2: wait until each subsystem signals completion
            logger.debug("Kernel waiting for subsystems to check in at tick %s", tick)
            self._barrier.wait()

            logger.debug(
                "Tick %s complete (queue size=%s)",
                tick,
                self.metrics_stream.qsize(),
            )
            time.sleep(self.tick_duration)

        self._running.clear()
        logger.debug("Kernel stopped after %s ticks", max_ticks)

    def wait_for_tick(self):
        # Called by subsystems to wait until the next tick begins.
        logger.debug("Thread %s waiting for next tick", threading.current_thread().name)
        self._barrier.wait()

    def collect_from_subsystem(self, payload):
        # Called by subsystems when they finish work for a tick.
        self.metrics_stream.put(payload)
        logger.debug(
            "Collected metrics from %s: %s (queue size=%s)",
            payload.get("subsystem"),
            {k: v for k, v in payload.items() if k != "subsystem"},
            self.metrics_stream.qsize(),
        )
        self._barrier.wait()

    def stop(self):
        self._running.clear()



