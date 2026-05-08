from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from yacht.regatta import ConfigError, load_regatta, run_regatta


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yacht",
        description="Run reproducible agentic coding harness regattas.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="Run a regatta config.")
    run_parser.add_argument("config", type=Path, help="Path to a regatta TOML file.")
    run_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where wake artifacts and scorecards are written.",
    )

    validate_parser = subcommands.add_parser(
        "validate",
        help="Validate a regatta config without running it.",
    )
    validate_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            scorecard = run_regatta(args.config, args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(scorecard, indent=2))
        return 0

    if args.command == "validate":
        try:
            regatta = load_regatta(args.config)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(f"valid regatta config: {regatta.name}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
