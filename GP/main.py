"""Entry point for the smart city simulation platform."""

from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from src.core.kernel import CityKernel
from src.utils.config import load_simulation_config
from src.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the simulation runner."""

    parser = argparse.ArgumentParser(
        description="Run the Smart City parallel simulation"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("src/data/scenario_default.json"),
        help="Path to the simulation configuration file",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        help="Maximum number of simulation ticks to execute (default: run until stopped)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity level",
    )
    parser.add_argument(
        "--mode",
        default="headless",
        choices=["headless", "visual", "report", "dash"],
        help="Execution mode: headless logging, matplotlib dashboard, offline report, or Dash control center",
    )
    parser.add_argument(
        "--history",
        type=int,
        default=240,
        help="Number of ticks retained in visual dashboard plots (visual mode only)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    configure_logging(args.log_level)
    logger = logging.getLogger(__name__)

    if args.ticks is not None and args.ticks <= 0:
        args.ticks = None

    if not args.config.exists():
        parser_hint = "Try generating a configuration file in src/data/"
        raise FileNotFoundError(f"Configuration file not found: {args.config}. {parser_hint}")

    config = load_simulation_config(args.config)

    if args.mode == "report" and args.ticks is None:
        args.ticks = int(config.get("report_ticks", 180))
        logger.info("Report mode without tick limit; defaulting to %d ticks.", args.ticks)

    kernel = CityKernel(
        config=config,
        tick_duration=config.get("tick_duration", 0.5),
        max_ticks=args.ticks,
    )

    logger.info(
        "Starting Smart City Simulation (tick_duration=%.2fs, max_ticks=%s)",
        kernel.tick_duration,
        "∞" if kernel.max_ticks is None else kernel.max_ticks,
    )

    kernel.bootstrap()

    if args.mode == "visual":
        _run_with_dashboard(kernel, args, logger)
    elif args.mode == "report":
        _run_with_report(kernel, args, logger)
    elif args.mode == "dash":
        _run_with_dash(kernel, logger, args)
    else:
        _run_headless(kernel, logger)


def _run_headless(kernel: CityKernel, logger: logging.Logger) -> None:
    try:
        kernel.run()
    except KeyboardInterrupt:
        logger.warning("Simulation interrupted by user")
    except Exception:
        logger.exception("Unexpected error in simulation loop")
        raise
    finally:
        logger.info("Shutting down simulation")
        kernel.shutdown()


def _run_with_dashboard(kernel: CityKernel, args: argparse.Namespace, logger: logging.Logger) -> None:
    from src.viz.dashboard import SimulationDashboard

    kernel_thread = threading.Thread(target=kernel.run, name="KernelThread", daemon=True)
    kernel_thread.start()
    logger.info("Kernel running in background thread; launching dashboard")

    dashboard = SimulationDashboard(kernel=kernel, history=args.history)
    try:
        dashboard.start()
    except KeyboardInterrupt:
        logger.warning("Dashboard interrupted by user")
    finally:
        logger.info("Stopping simulation and dashboard")
        kernel.shutdown()
        kernel_thread.join(timeout=3)


def _run_with_report(kernel: CityKernel, args: argparse.Namespace, logger: logging.Logger) -> None:
    from src.viz.report import TelemetryRecorder, render_static_dashboard
    import matplotlib.pyplot as plt

    if kernel.max_ticks is None:
        logger.info("No tick limit provided for report; defaulting to 180 ticks.")
        kernel.max_ticks = 180

    kernel_thread = threading.Thread(target=kernel.run, name="KernelThread", daemon=True)
    kernel_thread.start()
    logger.info("Kernel running in background thread; recording metrics")

    recorder = TelemetryRecorder(kernel)
    records = {}
    try:
        records = recorder.record(timeout=0.5)
    except KeyboardInterrupt:
        logger.warning("Recording interrupted by user")
    finally:
        kernel.shutdown()
        kernel_thread.join(timeout=3)

    if not kernel.is_running():
        logger.info("Simulation completed; rendering report")
        fig = render_static_dashboard(records or recorder.data)
        fig.canvas.manager.set_window_title("Smart City Simulation Report")
        plt.show()


def _run_with_dash(kernel: CityKernel, logger: logging.Logger, args: argparse.Namespace) -> None:
    from src.core.controller import SimulationController
    from src.viz.server import build_dashboard_app

    controller = SimulationController(kernel)
    app = build_dashboard_app(controller)

    try:
        logger.info("Starting Dash control center on http://127.0.0.1:8050")
        app.run(debug=False, use_reloader=False)
    except KeyboardInterrupt:
        logger.warning("Dash server interrupted by user")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()

