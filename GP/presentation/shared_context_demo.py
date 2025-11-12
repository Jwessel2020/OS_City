import threading
import logging

logger = logging.getLogger(__name__)

class SharedContext:
    # Thread-safe dictionary storing both metrics and controls.
    def __init__(self):
        self._lock = threading.RLock()
        self._metrics = {}
        self._controls = {"traffic_inflow": 1.0}

    # Mutators / accessors for metrics
    def update_metrics(self, subsystem, data):
        with self._lock:
            self._metrics[subsystem] = data
            logger.debug(
                "Metrics updated for %s: %s (thread=%s)",
                subsystem,
                data,
                threading.current_thread().name,
            )

    def snapshot_metrics(self):
        with self._lock:
            logger.debug(
                "Metrics snapshot requested (thread=%s)", threading.current_thread().name
            )
            return dict(self._metrics)

    # Mutators / accessors for controls
    def set_control(self, key, value):
        with self._lock:
            self._controls[key] = value
            logger.debug(
                "Control %s set to %s (thread=%s)",
                key,
                value,
                threading.current_thread().name,
            )

    def get_control(self, key, default=None):
        with self._lock:
            value = self._controls.get(key, default)
            logger.debug(
                "Control %s read as %s (thread=%s)",
                key,
                value,
                threading.current_thread().name,
            )
            return self._controls.get(key, default)


