from __future__ import annotations

import argparse

from app.config import load_settings
from app.logging import configure_logging
from app.pipeline import DailyDigestPipeline


def run_once(*, config_path: str, dry_run: bool, verbose: bool) -> int:
    configure_logging(verbose=verbose)
    settings = load_settings(config_path)
    pipeline = DailyDigestPipeline(settings)
    try:
        run_id = pipeline.run(dry_run=dry_run)
    finally:
        pipeline.close()

    print(f"Run completed successfully. run_id={run_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily arXiv Notify command line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_once_parser = subparsers.add_parser(
        "run-once",
        help="Run the full pipeline once.",
        description="Run the Daily arXiv Notify pipeline exactly once.",
    )
    run_once_parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to the TOML configuration file.",
    )
    run_once_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate artifacts without sending email.",
    )
    run_once_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run-once":
        return run_once(
            config_path=args.config,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
