"""City-wide simulation kernel orchestrating subsystem threads."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Iterable
from queue import Empty, Queue
from typing import Any, Deque, Optional

from src.core.analytics import CityAnalytics
from src.core.context import CityContext
from src.core.optimizer import CityOptimizer, ControlKnob, OptimizationGoal
from src.data.database import SimulationDatabase
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
        self.analytics = CityAnalytics(self.context)
        self.optimizer = CityOptimizer(self.context)
        
        buffer_size = int(self.config.get("metrics_buffer", 256))
        self._metrics_queue: Queue[dict[str, Any]] = Queue(maxsize=buffer_size)
        self._latest_metrics: dict[str, dict[str, Any]] = {}
        self._pause_event = threading.Event()
        self._pause_event.set()
        storage_cfg = config.get("database", {})
        self._storage_cfg = storage_cfg if isinstance(storage_cfg, dict) else {}
        self._storage: SimulationDatabase | None = None
        self._run_id: int | None = None
        self._run_open = False
        
        # OS-level metrics tracking
        self._deadlock_detected_count = 0
        self._intersection_wait_cycles: Deque[float] = deque(maxlen=100)
        self._resource_timeout_events = 0
        self._emergency_preemptions_count = 0
        self._starvation_events = 0
        self._priority_inversions = 0
        self._queue_overflow_events = 0
        self._lock_contention_times: Deque[float] = deque(maxlen=100)
        self._tick_latencies: Deque[float] = deque(maxlen=200)  # For p50/p99 calculation
        self._last_tick_start = 0.0
        self._last_barrier_wait_start = 0.0

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

        # Configure default optimization goals and knobs
        self.optimizer.add_knob(ControlKnob("traffic_signal_bias", 0.5, 1.8, 1.0))
        self.optimizer.add_knob(ControlKnob("traffic_inflow", 0.0, 3.0, 1.0))
        self.optimizer.add_knob(ControlKnob("energy_base_load", 0.2, 3.0, 1.0))
        self.optimizer.add_knob(ControlKnob("renewable_boost", 0.0, 1.0, 0.0))
        self.optimizer.add_knob(ControlKnob("waste_fleet_size", 2.0, 16.0, 6.0, step_size=1.0))
        self.optimizer.add_knob(ControlKnob("emergency_staff", 4.0, 24.0, 8.0, step_size=1.0))
        
        # Default goal: Balanced Efficiency
        self.optimizer.add_goal("minimize_congestion", OptimizationGoal("traffic.congestion_index", 0.6, weight=2.0))
        self.optimizer.add_goal("minimize_energy_price", OptimizationGoal("energy.price_index", 1.2, weight=1.0))
        self.optimizer.add_goal("minimize_waste_backlog", OptimizationGoal("waste.pending_requests", 20.0, weight=0.5))
        self.optimizer.add_goal("minimize_incidents", OptimizationGoal("emergency.open_incidents", 5.0, weight=3.0))
        
        # Activate optimizer by default? No, let user toggle it.
        self.optimizer.toggle(False)

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

        self._start_run_record()
        self._running.set()

        for subsystem in self._subsystems:
            subsystem.start()
            logger.info("Started subsystem thread %s", subsystem.name)

        logger.info("Kernel entering main loop with %d subsystems", len(self._subsystems))

        run_status = "completed"
        try:
            while self._should_continue():
                tick_start = time.perf_counter()
                self._last_tick_start = tick_start

                self._tick_event.set()
                barrier_start = time.perf_counter()
                self._last_barrier_wait_start = barrier_start
                barrier_wait_time = 0.0
                try:
                    # Track barrier wait time (intersection wait cycles)
                    self._tick_barrier.wait(timeout=self.tick_duration * 2.0)
                    barrier_wait_time = (time.perf_counter() - barrier_start) * 1000  # ms
                    self._intersection_wait_cycles.append(barrier_wait_time)
                except threading.BrokenBarrierError:
                    barrier_wait_time = (time.perf_counter() - barrier_start) * 1000  # ms
                    logger.warning("Tick barrier broken; terminating loop")
                    self._deadlock_detected_count += 1
                    self._resource_timeout_events += 1
                    break
                except Exception as e:
                    barrier_wait_time = (time.perf_counter() - barrier_start) * 1000  # ms
                    # Timeout or other barrier issue = potential deadlock/resource timeout
                    self._resource_timeout_events += 1
                    self._deadlock_detected_count += 1
                    logger.warning("Barrier wait failed: %s", e)
                    break
                finally:
                    self._tick_event.clear()
                    # Track lock contention (time spent waiting for barrier)
                    if barrier_wait_time > 10.0:  # Only track significant contention (>10ms)
                        self._lock_contention_times.append(barrier_wait_time)

                self._tick_index += 1
                
                # Run optimization step
                self.optimizer.step()
                
                # Run analytics periodically
                if self._tick_index % 10 == 0:
                    self.analytics.analyze()

                self._pause_event.wait()

                elapsed = time.perf_counter() - tick_start
                tick_latency_ms = elapsed * 1000
                self._tick_latencies.append(tick_latency_ms)
                
                # Check for queue overflow
                if self._metrics_queue.full():
                    self._queue_overflow_events += 1
                
                # Publish OS-level metrics every tick
                self._publish_os_metrics()
                
                sleep_time = max(self.tick_duration - elapsed, 0)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except Exception:
            run_status = "error"
            raise
        finally:
            if run_status == "completed" and not self._running.is_set():
                run_status = "stopped"
            self._running.clear()
            self._finalize_run(run_status)

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
        
        # Reset OS-level metrics
        self._deadlock_detected_count = 0
        self._intersection_wait_cycles.clear()
        self._resource_timeout_events = 0
        self._emergency_preemptions_count = 0
        self._starvation_events = 0
        self._priority_inversions = 0
        self._queue_overflow_events = 0
        self._lock_contention_times.clear()
        self._tick_latencies.clear()
        
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
        
        # Feed analytics engine
        self.analytics.track(subsystem, metrics)

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
        if self._storage and self._run_open and self._run_id is not None:
            try:
                self._storage.record_metrics(self._run_id, tick, subsystem, metrics)
            except Exception:
                logger.exception("Failed to persist metrics for subsystem %s", subsystem)

    def set_control_state(self, controls: dict[str, Any]) -> None:
        """Apply externally supplied control values."""

        paused = controls.get("paused")
        if isinstance(paused, bool):
            if paused:
                self._pause_event.clear()
            else:
                self._pause_event.set()

        self.context.update_controls(controls)
        if self._storage and self._run_open and self._run_id is not None:
            try:
                self._storage.record_control_event(self._run_id, controls)
            except Exception:
                logger.exception("Failed to persist control state update")

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

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _ensure_storage(self) -> None:
        if self._storage is not None:
            return
        if not self._storage_cfg.get("enabled"):
            return
        path = self._storage_cfg.get("path", "artifacts/smart_city.sqlite3")
        log_path = self._storage_cfg.get("log_path", "logs/sqlite_trace.log")
        self._storage = SimulationDatabase(path, log_path=log_path)

    def _start_run_record(self) -> None:
        self._ensure_storage()
        if self._storage is None or self._run_open:
            return
        label = self._storage_cfg.get("label") or self.config.get("run_label")
        self._run_id = self._storage.start_run(
            label=label,
            tick_duration=self.tick_duration,
            max_ticks=self.max_ticks,
            config=self.config,
        )
        self._run_open = True

    def _finalize_run(self, status: str) -> None:
        if not self._run_open or self._storage is None or self._run_id is None:
            return
        try:
            self._storage.complete_run(self._run_id, status=status)
        finally:
            self._run_open = False
            self._run_id = None
    
    # ------------------------------------------------------------------
    # OS-level metrics tracking
    # ------------------------------------------------------------------
    def _publish_os_metrics(self) -> None:
        """Calculate and publish OS-level metrics (deadlock, scheduling, concurrency, throughput/latency)."""
        
        # Calculate average intersection wait cycles
        avg_intersection_wait = (
            sum(self._intersection_wait_cycles) / len(self._intersection_wait_cycles)
            if self._intersection_wait_cycles else 0.0
        )
        
        # Calculate lock contention time
        avg_lock_contention = (
            sum(self._lock_contention_times) / len(self._lock_contention_times)
            if self._lock_contention_times else 0.0
        )
        
        # Calculate latency percentiles
        sorted_latencies = sorted(self._tick_latencies) if self._tick_latencies else []
        p50_latency = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0.0
        p99_index = int(len(sorted_latencies) * 0.99) if sorted_latencies else 0
        p99_latency = sorted_latencies[p99_index] if p99_index < len(sorted_latencies) else 0.0
        
        # Calculate system throughput score (inverse of latency, normalized)
        # Higher throughput = lower latency, more ticks completed
        avg_latency = sum(sorted_latencies) / len(sorted_latencies) if sorted_latencies else self.tick_duration * 1000
        target_latency = self.tick_duration * 1000
        throughput_score = max(0.0, min(1.0, target_latency / max(avg_latency, 1.0)))
        
        # Count active threads (subsystems + main kernel thread)
        active_threads = sum(1 for s in self._subsystems if s.is_alive()) + (1 if self._running.is_set() else 0)
        active_processes = 1  # Single process, multiple threads
        
        # Check for starvation (vehicles/trucks waiting too long)
        # This is tracked per subsystem, but we aggregate here
        traffic_wait = self.get_latest_metrics("traffic").get("avg_wait_min", 0.0)
        waste_pending = self.get_latest_metrics("waste").get("pending_requests", 0)
        starvation_threshold = 10.0  # minutes
        if traffic_wait > starvation_threshold or waste_pending > 50:
            self._starvation_events += 1
        
        # Track emergency preemptions (when emergency overrides normal operations)
        emergency_override = self.context.get_control("emergency_override", False)
        if emergency_override:
            self._emergency_preemptions_count += 1
        
        # Priority inversions: when low-priority tasks block high-priority ones
        # Detect when emergency incidents are delayed due to traffic/waste congestion
        emergency_open = self.get_latest_metrics("emergency").get("open_incidents", 0)
        traffic_congestion = self.get_latest_metrics("traffic").get("congestion_index", 0.0)
        if emergency_open > 0 and traffic_congestion > 0.8:
            self._priority_inversions += 1
        
        os_metrics = {
            # Deadlock metrics
            "deadlock_detected_count": self._deadlock_detected_count,
            "avg_intersection_wait_cycles": round(avg_intersection_wait, 2),
            "resource_timeout_events": self._resource_timeout_events,
            
            # Scheduling fairness
            "emergency_preemptions_count": self._emergency_preemptions_count,
            "starvation_events": self._starvation_events,
            "priority_inversions": self._priority_inversions,
            
            # Concurrency health
            "active_threads_count": active_threads,
            "active_processes_count": active_processes,
            "queue_overflow_events": self._queue_overflow_events,
            "lock_contention_time_ms": round(avg_lock_contention, 2),
            
            # Throughput vs Latency
            "system_throughput_score": round(throughput_score, 3),
            "p50_latency_ms": round(p50_latency, 2),
            "p99_latency_ms": round(p99_latency, 2),
            
            # Digital Twin Extensions
            "optimizer_status": self.optimizer.get_status(),
            "analytics_insights": self.analytics.get_insights(),
        }
        
        self.publish_metrics("kernel", os_metrics)

