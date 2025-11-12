# run_demo.py
# -----------
# Minimal driver that wires together the presentation snippets above and
# prints a short stream of metrics to the console.

import threading
import logging
from pathlib import Path

from city_kernel_demo import CityKernel
from shared_context_demo import SharedContext
from traffic_subsystem_demo import TrafficSubsystem


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("presentation/run_log.txt", mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)

    context = SharedContext()

    # Instantiate the kernel with an empty list; we'll attach subsystems after.
    kernel = CityKernel([], tick_duration=0.2)
    traffic = TrafficSubsystem(kernel, context)

    # Register the subsystems and rebuild the internal barrier.
    kernel.subsystems = [traffic]
    kernel._barrier = threading.Barrier(len(kernel.subsystems) + 1)

    # Collect metrics in a helper thread so we can display them in real-time.
    output = []

    def consume():
        while len(output) < 12:
            payload = kernel.metrics_stream.get()
            output.append(payload)
            print(f"[tick #{len(output):02d}] {payload}")

    consumer = threading.Thread(target=consume, name="metrics-consumer", daemon=True)
    consumer.start()

    # Run the kernel for a handful of ticks.
    kernel.run(max_ticks=12)

    # Stop the subsystem threads (because they're daemon threads the program
    # would exit anyway, but this keeps the demo tidy).
    traffic.stop()

    logger.info("Simulation completed. Final snapshot: %s", context.snapshot_metrics())

    Path("presentation/run_output.txt").write_text(
        "\n".join(f"[tick #{i+1:02d}] {payload}" for i, payload in enumerate(output)),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()


