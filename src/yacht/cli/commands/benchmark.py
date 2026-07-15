from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.cli import output
from yacht.domain.model import ConfigError
from yacht.reports.benchmark_aggregate import render_benchmark_aggregate
from yacht.reports.benchmark_readiness import render_benchmark_readiness_report
from yacht.reports.benchmark_scorecard import write_benchmark_scorecard
from yacht.workflows.benchmark_execution_plan import write_benchmark_execution_plan
from yacht.workflows.benchmark_grading_collection import (
    collect_benchmark_grading_reports,
)
from yacht.workflows.benchmark_launch import write_benchmark_launch_result
from yacht.workflows.benchmark_launcher_handoff import (
    DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
)
from yacht.workflows.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.workflows.readiness_gate import evaluate_readiness_gate


def register(subcommands: argparse._SubParsersAction) -> None:
    benchmark_scorecard_parser = subcommands.add_parser(
        "benchmark-scorecard",
        help="Write a scorecard summary from validated benchmark artifacts.",
    )
    benchmark_scorecard_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing handoff and grading artifacts.",
    )
    benchmark_scorecard_parser.set_defaults(handler=_benchmark_scorecard)

    benchmark_aggregate_parser = subcommands.add_parser(
        "benchmark-aggregate",
        help="Aggregate completed benchmark scorecards across logbooks.",
    )
    benchmark_aggregate_parser.add_argument(
        "--logbook",
        type=Path,
        action="append",
        required=True,
        help="Benchmark logbook directory to include. Pass once per run.",
    )
    benchmark_aggregate_parser.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="Output format for the aggregate report.",
    )
    benchmark_aggregate_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the aggregate report.",
    )
    benchmark_aggregate_parser.set_defaults(handler=_benchmark_aggregate)

    benchmark_plan_parser = subcommands.add_parser(
        "benchmark-plan",
        help="Write a dry-run benchmark execution readiness plan.",
    )
    benchmark_plan_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing handoff and benchmark artifacts.",
    )
    benchmark_plan_parser.set_defaults(handler=_benchmark_plan)

    readiness_report_parser = subcommands.add_parser(
        "benchmark-readiness-report",
        help="Print a benchmark readiness report.",
    )
    readiness_report_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing benchmark-execution-plan.json.",
    )
    readiness_report_parser.add_argument(
        "--format",
        choices=("text", "markdown", "json", "summary-json"),
        default="text",
        help="Output format for the readiness report.",
    )
    readiness_report_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered readiness report.",
    )
    readiness_report_parser.set_defaults(handler=_benchmark_readiness_report)

    readiness_gate_parser = subcommands.add_parser(
        "readiness-gate",
        help="Exit nonzero when benchmark readiness has blocked vessels.",
    )
    readiness_gate_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing benchmark-execution-plan.json.",
    )
    readiness_gate_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the readiness summary JSON.",
    )
    readiness_gate_parser.set_defaults(handler=_readiness_gate)

    benchmark_launcher_parser = subcommands.add_parser(
        "benchmark-launcher",
        help="Write native benchmark launcher commands without executing them.",
    )
    benchmark_launcher_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing handoff and benchmark artifacts.",
    )
    benchmark_launcher_parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="SWE-bench --max_workers value to include in generated commands.",
    )
    benchmark_launcher_parser.add_argument(
        "--python-executable",
        default=DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
        help="Python executable prefix to include in generated SWE-bench commands.",
    )
    benchmark_launcher_parser.set_defaults(handler=_benchmark_launcher)

    benchmark_launch_parser = subcommands.add_parser(
        "benchmark-launch",
        help="Execute ready native benchmark launcher commands.",
    )
    benchmark_launch_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing benchmark-launcher-handoff.json.",
    )
    benchmark_launch_parser.set_defaults(handler=_benchmark_launch)

    benchmark_collect_grading_parser = subcommands.add_parser(
        "benchmark-collect-grading",
        help="Collect native benchmark reports into validated grading artifacts.",
    )
    benchmark_collect_grading_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    benchmark_collect_grading_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing benchmark launch artifacts.",
    )
    benchmark_collect_grading_parser.set_defaults(handler=_benchmark_collect_grading)


def _benchmark_scorecard(args: argparse.Namespace) -> int:
    try:
        scorecard = write_benchmark_scorecard(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(scorecard, indent=2))
    return 0


def _benchmark_aggregate(args: argparse.Namespace) -> int:
    try:
        report = render_benchmark_aggregate(args.logbook, args.format)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    return output.emit_report(report, args.output)


def _benchmark_plan(args: argparse.Namespace) -> int:
    try:
        plan = write_benchmark_execution_plan(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2))
    return 0


def _benchmark_readiness_report(args: argparse.Namespace) -> int:
    try:
        report = render_benchmark_readiness_report(args.logbook, args.format)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    return output.emit_report(report, args.output)


def _readiness_gate(args: argparse.Namespace) -> int:
    try:
        gate = evaluate_readiness_gate(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(gate.summary_json, encoding="utf-8")
    else:
        print(gate.summary_json, end="")
    if gate.blocked_vessel_count:
        print(
            f"readiness gate blocked: {gate.blocked_vessel_count} blocked vessel(s)",
            file=sys.stderr,
        )
    return gate.exit_code


def _benchmark_launcher(args: argparse.Namespace) -> int:
    try:
        launcher_handoff = write_benchmark_launcher_handoff(
            logbook_dir=args.logbook,
            max_workers=args.max_workers,
            python_executable=args.python_executable,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(launcher_handoff, indent=2))
    return 0


def _benchmark_launch(args: argparse.Namespace) -> int:
    try:
        launch_result = write_benchmark_launch_result(logbook_dir=args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(launch_result, indent=2))
    return 0 if launch_result["status"] in {"complete", "partial"} else 1


def _benchmark_collect_grading(args: argparse.Namespace) -> int:
    try:
        collection = collect_benchmark_grading_reports(
            config_path=args.config,
            logbook_dir=args.logbook,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(collection, indent=2))
    return 0 if collection["status"] in {"complete", "partial"} else 1
