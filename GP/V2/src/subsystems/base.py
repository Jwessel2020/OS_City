import threading
import time
import logging
from typing import Optional

from src.core.metrics import TickEvent, MetricEvent

logger = logging.getLogger("Subsystem")

class Subsystem(threading.Thread):
    """
    Base class for all city subsystems.
    
    OS Concepts:
    - Threading: Each subsystem runs as an independent OS thread.
    - Scheduling: We implement a manual 'tick' loop with drift compensation.
    - Instrumentation: We measure work time vs sleep time (CPU utilization).
    """
    
    def __init__(self, name: str, simulation, interval: float = 1.0):
        super().__init__(name=name, daemon=True)
        self.name = name
        self.simulation = simulation
        self.interval = interval # Target tick duration in seconds
        self.last_tick_ts = time.time()
        self.tick_count = 0
        
    def run(self):
        logger.info(f"[{self.name}] Thread Started (TID: {threading.get_native_id()})")
        
        next_tick_time = time.perf_counter()
        
        while self.simulation.running.is_set():
            loop_start = time.perf_counter()
            
            # 1. Do Work
            self.execute_tick()
            self.last_tick_ts = time.time()
            self.tick_count += 1
            
            # 2. Measure Timing
            work_end = time.perf_counter()
            work_duration = (work_end - loop_start) * 1000.0 # ms
            
            # 3. Schedule Next Tick (Drift Compensation)
            next_tick_time += self.interval
            sleep_duration = next_tick_time - time.perf_counter()
            
            # Log Tick Metrics
            latency = (time.perf_counter() - loop_start) * 1000.0
            drift = (time.perf_counter() - next_tick_time) * 1000.0
            
            self.simulation.logger.log(TickEvent(
                run_id=self.simulation.logger.run_id,
                subsystem=self.name,
                tick_seq=self.tick_count,
                latency_ms=latency,
                drift_ms=drift,
                work_time_ms=work_duration
            ))
            
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            else:
                # We are running behind! Yield to let others run.
                time.sleep(0.01)

    def execute_tick(self):
        """Override this method to perform subsystem logic."""
        pass

    def log_metric(self, payload: dict):
        """Helper to log custom metrics."""
        self.simulation.logger.log(MetricEvent(
            run_id=self.simulation.logger.run_id,
            subsystem=self.name,
            payload=payload
        ))

