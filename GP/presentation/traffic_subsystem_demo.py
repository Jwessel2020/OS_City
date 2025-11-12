import random
import logging

from subsystem_base_demo import SubsystemThread
from shared_context_demo import SharedContext

logger = logging.getLogger(__name__)


class TrafficSubsystem(SubsystemThread):
    # Models vehicle throughput and congestion influenced by control sliders.
    def __init__(self, kernel, context: SharedContext):
        super().__init__(kernel, name="traffic")
        self.context = context
        self._rng = random.Random(42)
        self.vehicles = 40
        self.congestion = 0.3

    def execute_tick(self):
        # Read live control knob (0.4–2.0 multiplier) from the shared context
        inflow = self.context.get_control("traffic_inflow", 1.0)

        variability = self._rng.randint(-5, 5)
        self.vehicles = max(20, int(self.vehicles * inflow) + variability)
        self.congestion = min(1.0, max(0.0, self.congestion + variability / 200))
        logger.debug(
            "Traffic execute_tick: inflow=%s variability=%s -> vehicles=%s, congestion=%s",
            inflow,
            variability,
            self.vehicles,
            round(self.congestion, 3),
        )

    def collect_metrics(self):
        metrics = {
            "vehicles": self.vehicles,
            "congestion_index": round(self.congestion, 2),
        }
        self.context.update_metrics(self.name, metrics)
        logger.debug("Traffic metrics reported: %s", metrics)
        return {"subsystem": self.name, **metrics}


