import time
import random
from src.subsystems.base import Subsystem
from src.core.buffer import BoundedBuffer

class TrafficSubsystem(Subsystem):
    """
    PRODUCER: Simulates traffic and generates EV charging requests.
    """
    
    def __init__(self, name, simulation, ev_buffer: BoundedBuffer, interval=0.5):
        super().__init__(name, simulation, interval)
        self.ev_buffer = ev_buffer
        self.cars_on_road = 100

    def execute_tick(self):
        # 1. Simulate Traffic Logic (CPU work)
        # Random fluctuation
        change = random.randint(-5, 5)
        self.cars_on_road = max(0, min(500, self.cars_on_road + change))
        
        # Simulate some calculation time
        time.sleep(random.uniform(0.01, 0.05))
        
        # 2. Produce EV Charging Requests
        # PRODUCE AGGRESSIVELY: Try to produce 2-4 items per tick to flood the buffer
        num_requests = random.randint(2, 4)
        
        for _ in range(num_requests):
            req_id = f"EV-{self.tick_count}-{random.randint(0,99)}"
            request = {"id": req_id, "kwh": random.randint(20, 80), "ts": time.time()}
            
            # BLOCKING PUT: Wait for space in buffer
            try:
                success = self.ev_buffer.put(request, timeout=0.2)
                if not success:
                    self.log_metric({"event": "ev_req_dropped", "reason": "timeout_full"})
            except ValueError:
                pass # Buffer closed
        
        # 3. Log Status
        self.log_metric({
            "cars": self.cars_on_road, 
            "congestion": self.cars_on_road / 500.0
        })

