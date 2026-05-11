from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from yacht.benchmark_execution_plan import write_benchmark_execution_plan
from yacht.benchmark_launcher_handoff import native_report_path_from_launcher_handoff
from yacht.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.benchmark_scorecard import write_benchmark_scorecard
from yacht.course_handoff import write_course_handoff
from yacht.local_smoke_adapter import LocalSmokeAgentAdapter
from yacht.pi_adapter import PiAdapter, SubprocessPiPromptLauncher
from yacht.preflight_runner import (
    AgentPromptRunnerFactory,
    build_preflight_execution_plan,
    parse_secret_values,
    run_preflight,
)
from yacht.regatta import ConfigError, load_regatta, run_regatta
from yacht.runtime_plan import build_runtime_plan
from yacht.swebench_grading import write_swe_bench_grading_report
from yacht.swebench_predictions import write_swe_bench_predictions


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
    validate_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for validation results.",
    )

    plan_parser = subcommands.add_parser(
        "plan",
        help="Print a redacted runtime/preflight plan without launching agents.",
    )
    plan_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )

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
        default="python",
        help="Python executable prefix to include in generated SWE-bench commands.",
    )

    preflight_parser = subcommands.add_parser(
        "preflight",
        help="Run machine preflight checks without running benchmark tasks.",
    )
    preflight_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    preflight_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where preflight artifacts are written.",
    )
    preflight_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    preflight_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )
    preflight_parser.add_argument(
        "--agent-preflight",
        choices=("none", "pi", "local-smoke"),
        default="none",
        help="Opt into agent-prompt preflight checks with the selected adapter.",
    )
    preflight_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved preflight execution plan without running checks.",
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
            if args.format == "json":
                _print_json({"valid": False, "error": str(error)})
                return 1
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.format == "json":
            _print_json({"valid": True, "regatta": regatta.name})
            return 0
        print(f"valid regatta config: {regatta.name}")
        return 0

    if args.command == "plan":
        try:
            plan = build_runtime_plan(args.config)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(plan, indent=2))
        return 0

    if args.command == "handoff":
        try:
            handoff = write_course_handoff(args.config, args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(handoff, indent=2))
        return 0

    if args.command == "predictions":
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

    if args.command == "grading-report":
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

    if args.command == "benchmark-scorecard":
        try:
            scorecard = write_benchmark_scorecard(args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(scorecard, indent=2))
        return 0

    if args.command == "benchmark-plan":
        try:
            plan = write_benchmark_execution_plan(args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(plan, indent=2))
        return 0

    if args.command == "benchmark-launcher":
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

    if args.command == "preflight":
        try:
            if args.dry_run:
                summary = build_preflight_execution_plan(
                    args.config,
                    args.logbook,
                    args.workspace,
                    args.agent_preflight,
                )
                print(json.dumps(summary, indent=2))
                return 0
            summary = run_preflight(
                args.config,
                args.logbook,
                args.workspace,
                parse_secret_values(args.secret),
                agent_prompt_runner_factory=_agent_prompt_runner_factory(
                    args.agent_preflight
                ),
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] == "passed" else 1

    parser.error(f"unknown command: {args.command}")
    return 2


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2))


def _agent_prompt_runner_factory(
    adapter_name: str,
) -> AgentPromptRunnerFactory | None:
    if adapter_name == "none":
        return None
    if adapter_name == "pi":
        adapter = PiAdapter(launcher=SubprocessPiPromptLauncher())
        return lambda instance, transcript_dir: adapter.agent_prompt_runner(
            instance=instance,
            transcript_dir=transcript_dir,
        )
    if adapter_name == "local-smoke":
        adapter = LocalSmokeAgentAdapter()
        return lambda instance, transcript_dir: adapter.agent_prompt_runner(
            instance=instance,
            transcript_dir=transcript_dir,
        )
    raise ConfigError(f"unsupported agent preflight adapter {adapter_name}")
