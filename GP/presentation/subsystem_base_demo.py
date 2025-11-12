# subsystem_base_demo.py

import threading
import logging

logger = logging.getLogger(__name__)


class SubsystemThread(threading.Thread):
    # Reusable thread skeleton that each subsystem inherits from.
    def __init__(self, kernel, name):
        super().__init__(name=name, daemon=True)
        self.kernel = kernel
        self._stop = threading.Event()

    def run(self):
        self.on_start()
        logger.debug("Thread %s entering main loop", self.name)
        while not self._stop.is_set():
            self.kernel.wait_for_tick()
            if self._stop.is_set():
                break
            self.before_tick()
            self.execute_tick()
            self.after_tick()
            logger.debug("Thread %s pushing metrics", self.name)
            self.kernel.collect_from_subsystem(self.collect_metrics())

    def stop(self):
        self._stop.set()
        logger.debug("Thread %s marked for stop", self.name)

    # Hooks for subclasses
    def on_start(self):
        logger.debug("Thread %s starting (ident=%s)", self.name, threading.get_ident())
        pass

    def before_tick(self):
        logger.debug("Thread %s before_tick", self.name)
        pass

    def execute_tick(self):
        raise NotImplementedError

    def after_tick(self):
        logger.debug("Thread %s after_tick", self.name)
        pass

    def collect_metrics(self):
        return {"subsystem": self.name}


