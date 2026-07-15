from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.courses.handoff import write_course_handoff
from yacht.courses.swe_bench.grading import write_swe_bench_grading_report
from yacht.courses.swe_bench.predictions import write_swe_bench_predictions
from yacht.courses.swe_bench.predictions_from_attempts import (
    write_swe_bench_predictions_from_attempts,
)
from yacht.domain.model import ConfigError
from yacht.workflows.benchmark_launcher_handoff import (
    native_report_path_from_launcher_handoff,
)


def register(subcommands: argparse._SubParsersAction) -> None:
    handoff_parser = subcommands.add_parser(
        "handoff",
        help="Write a planned course adapter handoff artifact without running it.",
    )
    handoff_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    handoff_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where the course handoff artifact is written.",
    )
    handoff_parser.set_defaults(handler=_handoff)

    predictions_parser = subcommands.add_parser(
        "predictions",
        help="Validate and write SWE-bench candidate patch predictions.",
    )
    predictions_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    predictions_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="JSON file containing SWE-bench prediction records.",
    )
    predictions_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where candidate patch predictions are written.",
    )
    predictions_parser.add_argument(
        "--vessel",
        help="Optional comparison vessel name for per-vessel candidate patches.",
    )
    predictions_parser.set_defaults(handler=_predictions)

    predictions_from_attempts_parser = subcommands.add_parser(
        "predictions-from-attempts",
        help="Write SWE-bench candidate patches from task attempt artifacts.",
    )
    predictions_from_attempts_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    predictions_from_attempts_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing task attempt artifacts.",
    )
    predictions_from_attempts_parser.add_argument(
        "--vessel",
        required=True,
        help="Comparison vessel name whose task attempts should become predictions.",
    )
    predictions_from_attempts_parser.add_argument(
        "--comparison",
        help=(
            "Optional comparison name when the vessel has attempts in multiple "
            "comparisons."
        ),
    )
    predictions_from_attempts_parser.set_defaults(handler=_predictions_from_attempts)

    grading_report_parser = subcommands.add_parser(
        "grading-report",
        help="Validate and write a SWE-bench grading report artifact.",
    )
    grading_report_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    grading_report_source = grading_report_parser.add_mutually_exclusive_group(
        required=True
    )
    grading_report_source.add_argument(
        "--input",
        type=Path,
        help="JSON report produced by the SWE-bench harness.",
    )
    grading_report_source.add_argument(
        "--from-launcher",
        action="store_true",
        help=(
            "Read the expected SWE-bench report path from the benchmark launcher "
            "handoff for the selected vessel."
        ),
    )
    grading_report_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing candidate patches and receiving the report.",
    )
    grading_report_parser.add_argument(
        "--vessel",
        help="Optional comparison vessel name for per-vessel grading artifacts.",
    )
    grading_report_parser.set_defaults(handler=_grading_report)


def _handoff(args: argparse.Namespace) -> int:
    try:
        handoff = write_course_handoff(args.config, args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(handoff, indent=2))
    return 0


def _predictions(args: argparse.Namespace) -> int:
    try:
        summary = write_swe_bench_predictions(
            config_path=args.config,
            predictions_path=args.input,
            logbook_dir=args.logbook,
            vessel_name=args.vessel,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


def _predictions_from_attempts(args: argparse.Namespace) -> int:
    try:
        summary = write_swe_bench_predictions_from_attempts(
            config_path=args.config,
            logbook_dir=args.logbook,
            vessel_name=args.vessel,
            comparison_name=args.comparison,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


def _grading_report(args: argparse.Namespace) -> int:
    try:
        native_report_path = args.input
        if args.from_launcher:
            if not args.vessel:
                raise ConfigError(
                    "--from-launcher requires --vessel because launcher handoffs "
                    "are per vessel"
                )
            native_report_path = native_report_path_from_launcher_handoff(
                logbook_dir=args.logbook,
                vessel_name=args.vessel,
            )
        summary = write_swe_bench_grading_report(
            config_path=args.config,
            native_report_path=native_report_path,
            logbook_dir=args.logbook,
            vessel_name=args.vessel,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0
