from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.cli import output
from yacht.config.loader import load_regatta
from yacht.domain.model import ConfigError, run_regatta
from yacht.runtimes.plan import build_runtime_plan


def register(subcommands: argparse._SubParsersAction) -> None:
    run_parser = subcommands.add_parser("run", help="Run a regatta config.")
    run_parser.add_argument("config", type=Path, help="Path to a regatta TOML file.")
    run_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where wake artifacts and scorecards are written.",
    )
    run_parser.set_defaults(handler=_run)

    validate_parser = subcommands.add_parser(
        "validate",
        help="Validate a regatta config without running it.",
    )
    validate_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    validate_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for validation results.",
    )
    validate_parser.set_defaults(handler=_validate)

    plan_parser = subcommands.add_parser(
        "plan",
        help="Print a redacted runtime/preflight plan without launching agents.",
    )
    plan_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    plan_parser.set_defaults(handler=_plan)


def _run(args: argparse.Namespace) -> int:
    try:
        scorecard = run_regatta(args.config, args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(scorecard, indent=2))
    return 0


def _validate(args: argparse.Namespace) -> int:
    try:
        regatta = load_regatta(args.config)
    except ConfigError as error:
        if args.format == "json":
            output.print_json({"valid": False, "error": str(error)})
            return 1
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        output.print_json({"valid": True, "regatta": regatta.name})
        return 0
    print(f"valid regatta config: {regatta.name}")
    return 0


def _plan(args: argparse.Namespace) -> int:
    try:
        plan = build_runtime_plan(args.config)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2))
    return 0
