import threading
import time
import logging
from typing import Optional

from src.data.database import SqlLogger
from src.core.buffer import BoundedBuffer
from src.core.metrics import MetricEvent

# Import subsystems lazily or forward declare to avoid circular deps
# from src.subsystems.traffic import TrafficSubsystem
# from src.subsystems.energy import EnergySubsystem

logger = logging.getLogger("CitySimulation")

class CitySimulation:
    """
    The Micro-Kernel that orchestrates the OS simulation.
    
    OS Concepts:
    - Kernel: The core supervisor managing resources and processes (threads).
    - Inter-Process Communication (IPC): Setup of shared buffers between subsystems.
    - Watchdog: Detecting deadlocks and starvation.
    """
    
    def __init__(self):
        self.running = threading.Event()
        self.logger = SqlLogger()
        
        # IPC: Bounded Buffer between Traffic (Prod) and Energy (Cons)
        # Represents EV charging demand flowing from cars to grid.
        self.ev_buffer = BoundedBuffer(capacity=10, name="EV_Charging_Queue")
        
        self.subsystems = []
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="Watchdog", daemon=True)

    def bootstrap(self):
        """Initialize subsystems and wiring."""
        # Only start logger if not already running
        if not self.logger._running:
             self.logger.start()
        
        # We need to import here to avoid circular imports with type checking
        from src.subsystems.traffic import TrafficSubsystem
        from src.subsystems.energy import EnergySubsystem
        
        # Initialize Subsystems
        # Traffic produces EV requests -> ev_buffer
        traffic = TrafficSubsystem(
            name="Traffic", 
            simulation=self, 
            ev_buffer=self.ev_buffer,
            interval=0.5
        )
        
        # Energy consumes EV requests <- ev_buffer
        energy = EnergySubsystem(
            name="Energy", 
            simulation=self, 
            ev_buffer=self.ev_buffer,
            interval=0.5
        )
        
        self.subsystems = [traffic, energy]
        logger.info("Simulation Bootstrapped. Subsystems: %s", [s.name for s in self.subsystems])

    def start(self):
        """Start all threads."""
        if self.running.is_set():
            return
            
        self.running.set()
        
        for s in self.subsystems:
            s.start()
            
        self._watchdog_thread.start()
        logger.info("Simulation Started.")

    def stop(self):
        """Graceful shutdown signal."""
        logger.info("Stopping Simulation...")
        self.running.clear()
        
        # Signal buffer close to unblock any waiting threads
        self.ev_buffer.close()
        
        for s in self.subsystems:
            s.join(timeout=1.0)
            
        self.logger.stop()
        logger.info("Simulation Stopped.")

    def _watchdog_loop(self):
        """
        Monitor system health.
        Detects:
        1. Deadlocks (No tick progress)
        2. Starvation (Buffer full/empty for too long)
        """
        while self.running.is_set():
            time.sleep(2.0) # Check every 2 seconds
            
            now = time.time()
            
            # 1. Check Subsystem Liveness
            for s in self.subsystems:
                time_since_tick = now - s.last_tick_ts
                if time_since_tick > 5.0:
                    logger.warning(f"WATCHDOG: {s.name} stalled! No tick for {time_since_tick:.1f}s")
                    self.logger.log(MetricEvent(
                        run_id=self.logger.run_id,
                        subsystem="Kernel",
                        payload={"event": "stall_detected", "target": s.name, "duration": time_since_tick}
                    ))

            # 2. Check Buffer Health
            q_size = self.ev_buffer.qsize()
            if q_size == self.ev_buffer.capacity:
                logger.warning(f"WATCHDOG: {self.ev_buffer.name} is FULL ({q_size}). Potential backpressure/deadlock.")
            elif q_size == 0:
                # Not necessarily bad, but useful info
                pass
            
            # Log Queue Stats
            # We use try_put indirectly by logging a MetricEvent that the writer consumes
            # But wait, the Logger handles MetricEvents.
            # Let's actually use the logger to log queue stats
            from src.core.metrics import QueueStatEvent
            self.logger.log(QueueStatEvent(
                run_id=self.logger.run_id,
                subsystem="Kernel",
                queue_name=self.ev_buffer.name,
                size=q_size,
                capacity=self.ev_buffer.capacity,
                dropped=self.ev_buffer.stats["drop_count"]
            ))

