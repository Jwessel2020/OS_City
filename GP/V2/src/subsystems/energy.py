import time
import random
from src.subsystems.base import Subsystem
from src.core.buffer import BoundedBuffer

class EnergySubsystem(Subsystem):
    """
    CONSUMER: Manages Grid and processes EV charging requests.
    """
    
    def __init__(self, name, simulation, ev_buffer: BoundedBuffer, interval=0.5):
        super().__init__(name, simulation, interval)
        self.ev_buffer = ev_buffer
        self.base_load_mw = 50.0
        self.ev_load_mw = 0.0

    def execute_tick(self):
        # 1. Process Incoming EV Requests (Consumer Logic)
        # SLOW CONSUMER: Only process 1 request every other tick to cause backup
        processed_kwh = 0
        requests_processed = 0
        
        # Simulate being busy/slow
        time.sleep(0.2)
        
        # Only consume 1 item max per tick
        try:
            item = self.ev_buffer.get(timeout=0.1)
            if item:
                processed_kwh += item["kwh"]
                requests_processed += 1
        except StopIteration:
            pass # Buffer closed
        
        # 2. Update Grid State
        self.ev_load_mw = processed_kwh / 1000.0 # Fake conversion
        total_load = self.base_load_mw + self.ev_load_mw
        
        # Simulate Grid Physics (CPU work)
        time.sleep(random.uniform(0.02, 0.08))
        
        # 3. Log Metrics
        self.log_metric({
            "total_load_mw": total_load,
            "ev_load_mw": self.ev_load_mw,
            "requests_processed": requests_processed
        })

