"""Entry point for the smart city simulation platform."""

from __future__ import annotations

import argparse
import logging
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    configure_logging(args.log_level)
    logger = logging.getLogger(__name__)

    if not args.config.exists():
        parser_hint = "Try generating a configuration file in src/data/"
        raise FileNotFoundError(f"Configuration file not found: {args.config}. {parser_hint}")

    config = load_simulation_config(args.config)

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


if __name__ == "__main__":
    main()

