from __future__ import annotations

from app.cli import run_once


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Daily arXiv Notify pipeline once.")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to the TOML configuration file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate artifacts without sending email.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    return run_once(
        config_path=args.config,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
