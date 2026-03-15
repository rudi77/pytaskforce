"""CLI entry point for AutoOptim.

Usage:
    autooptim run --config my_optimization.yaml
    autooptim run --config config.yaml --max-iterations 20 --resume
"""

import argparse
import logging
import sys

from autooptim.config_loader import load_config
from autooptim.runner import run

logger = logging.getLogger(__name__)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="autooptim",
        description="AutoOptim: LLM-driven iterative optimization framework",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'run' command
    run_parser = subparsers.add_parser("run", help="Run an optimization loop")
    run_parser.add_argument(
        "--config",
        "-c",
        required=True,
        help="Path to the optimization config YAML file",
    )
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Override max iterations (0=unlimited)",
    )
    run_parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        help="Override max cost budget in USD",
    )
    run_parser.add_argument(
        "--eval-mode",
        choices=["quick", "full"],
        default=None,
        help="Override eval mode",
    )
    run_parser.add_argument(
        "--eval-runs",
        type=int,
        default=None,
        help="Override number of eval runs per experiment",
    )
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the most recent log",
    )
    run_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        _setup_logging(args.log_level)

        config = load_config(args.config)

        # Apply CLI overrides
        if args.max_iterations is not None:
            config.max_iterations = args.max_iterations
        if args.max_cost_usd is not None:
            config.max_cost_usd = args.max_cost_usd
        if args.eval_mode is not None:
            config.eval_mode = args.eval_mode
        if args.eval_runs is not None:
            config.eval_runs = args.eval_runs
        if args.resume:
            config.resume = True

        logger.info("AutoOptim starting: %s", config.name)
        logger.info("  categories: %s", list(config.categories.keys()))
        logger.info("  eval_mode: %s", config.eval_mode)
        logger.info("  proposer_model: %s", config.proposer.model)
        logger.info("  tolerance: %.3f", config.tolerance)
        logger.info("  max_iterations: %s", config.max_iterations or "unlimited")
        logger.info("  max_cost: $%.2f", config.max_cost_usd)

        try:
            run(config)
        except KeyboardInterrupt:
            logger.info("\nInterrupted by user. State saved for resume.")
            sys.exit(0)
        except Exception:
            logger.exception("AutoOptim failed with unexpected error")
            sys.exit(1)


if __name__ == "__main__":
    main()
