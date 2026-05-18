from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from yacht.benchmark_aggregate import render_benchmark_aggregate
from yacht.benchmark_execution_plan import write_benchmark_execution_plan
from yacht.benchmark_grading_collection import collect_benchmark_grading_reports
from yacht.benchmark_launch import write_benchmark_launch_result
from yacht.benchmark_launcher_handoff import DEFAULT_SWEBENCH_PYTHON_EXECUTABLE
from yacht.benchmark_launcher_handoff import native_report_path_from_launcher_handoff
from yacht.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.benchmark_readiness_report import render_benchmark_readiness_report
from yacht.benchmark_report import render_benchmark_report
from yacht.benchmark_scorecard import write_benchmark_scorecard
from yacht.benchmark_status import render_benchmark_status
from yacht.course_handoff import write_course_handoff
from yacht.local_smoke_adapter import LocalSmokeAgentAdapter
from yacht.local_smoke_eval import run_local_smoke_eval
from yacht.preflight_evidence_report import write_preflight_evidence_report
from yacht.pi_adapter import (
    PiAdapter,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
)
from yacht.pi_smoke_eval import run_pi_smoke_eval
from yacht.preflight_runner import (
    AgentPromptRunnerFactory,
    build_preflight_execution_plan,
    parse_secret_values,
    run_preflight,
)
from yacht.readiness_gate import evaluate_readiness_gate
from yacht.real_benchmark_eval import run_real_benchmark_eval
from yacht.real_benchmark_repetitions import run_real_benchmark_repetitions
from yacht.real_benchmark_runbook import render_real_benchmark_runbook
from yacht.real_benchmark_runbook import write_real_benchmark_runbook
from yacht.real_smoke_eval import run_real_smoke_eval
from yacht.real_smoke_runbook import render_real_smoke_runbook
from yacht.real_smoke_runbook import write_real_smoke_runbook
from yacht.regatta import ConfigError, load_regatta, run_regatta
from yacht.runtime_instances import build_runtime_instances_plan
from yacht.runtime_instances import write_runtime_instances_plan
from yacht.runtime_plan import build_runtime_plan
from yacht.swebench_grading import write_swe_bench_grading_report
from yacht.swebench_predictions import write_swe_bench_predictions
from yacht.swebench_predictions_from_attempts import (
    write_swe_bench_predictions_from_attempts,
)
from yacht.smoke_report import render_smoke_report
from yacht.smoke_readiness_report import write_smoke_readiness_report
from yacht.task_attempt_runner import TaskAgent, run_task_attempts
from yacht.task_attempt_scorecard import write_task_attempt_scorecard


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

    runtime_instances_parser = subcommands.add_parser(
        "runtime-instances",
        help="Print dry-run host runtime instance resolution without launching agents.",
    )
    runtime_instances_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    runtime_instances_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory used to resolve per-trial runtime paths.",
    )
    runtime_instances_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    runtime_instances_parser.add_argument(
        "--write-logbook",
        action="store_true",
        help="Write the resolved plan to logbook/runtime-instances.json.",
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

    benchmark_report_parser = subcommands.add_parser(
        "benchmark-report",
        help="Print a human-readable benchmark scorecard report.",
    )
    benchmark_report_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing benchmark-scorecard.json.",
    )
    benchmark_report_parser.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="Output format for the rendered benchmark report.",
    )
    benchmark_report_parser.add_argument(
        "--vessel",
        help="Only show per-vessel details for this vessel name.",
    )
    benchmark_report_parser.add_argument(
        "--task",
        help="Only show per-vessel details for this benchmark task id.",
    )
    benchmark_report_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered benchmark report.",
    )

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

    benchmark_status_parser = subcommands.add_parser(
        "benchmark-status",
        help="Print a checklist-style benchmark artifact status report.",
    )
    benchmark_status_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing benchmark artifacts.",
    )
    benchmark_status_parser.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="Output format for the rendered status report.",
    )
    benchmark_status_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered status report.",
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

    preflight_report_parser = subcommands.add_parser(
        "preflight-report",
        help="Write a preflight evidence eligibility report without running checks.",
    )
    preflight_report_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing handoff and preflight artifacts.",
    )

    smoke_readiness_report_parser = subcommands.add_parser(
        "smoke-readiness-report",
        help="Check whether a smoke logbook has usable preflight and task evidence.",
    )
    smoke_readiness_report_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing smoke eval artifacts.",
    )

    smoke_report_parser = subcommands.add_parser(
        "smoke-report",
        help="Print a human-readable smoke eval report.",
    )
    smoke_report_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help=(
            "Directory containing smoke-readiness-report.json and "
            "task-attempt-scorecard.json."
        ),
    )
    smoke_report_parser.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="Output format for the rendered smoke report.",
    )
    smoke_report_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered smoke report.",
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

    task_attempts_parser = subcommands.add_parser(
        "task-attempts",
        help="Run task attempts and write per-task agent evidence artifacts.",
    )
    task_attempts_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    task_attempts_parser.add_argument(
        "--agent",
        required=True,
        choices=("local-smoke", "pi"),
        help="Task attempt agent adapter to launch.",
    )
    task_attempts_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where task attempt artifacts are written.",
    )
    task_attempts_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    task_attempts_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )

    task_attempt_scorecard_parser = subcommands.add_parser(
        "task-attempt-scorecard",
        help="Write a scorecard summary from task attempt artifacts.",
    )
    task_attempt_scorecard_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory containing task attempt artifacts.",
    )

    local_smoke_eval_parser = subcommands.add_parser(
        "local-smoke-eval",
        help="Run local smoke task attempts and write the task attempt scorecard.",
    )
    local_smoke_eval_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    local_smoke_eval_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where local smoke eval artifacts are written.",
    )
    local_smoke_eval_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    local_smoke_eval_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )

    pi_smoke_eval_parser = subcommands.add_parser(
        "pi-smoke-eval",
        help="Run Pi smoke task attempts and write the task attempt scorecard.",
    )
    pi_smoke_eval_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    pi_smoke_eval_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where Pi smoke eval artifacts are written.",
    )
    pi_smoke_eval_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    pi_smoke_eval_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )

    real_smoke_eval_parser = subcommands.add_parser(
        "real-smoke-eval",
        help="Run Pi agent preflight, Pi smoke attempts, and smoke readiness.",
    )
    real_smoke_eval_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    real_smoke_eval_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where real smoke eval artifacts are written.",
    )
    real_smoke_eval_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    real_smoke_eval_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )

    real_benchmark_eval_parser = subcommands.add_parser(
        "real-benchmark-eval",
        help="Run Pi preflight, task attempts, native benchmark launch, and scorecard.",
    )
    real_benchmark_eval_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    real_benchmark_eval_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where real benchmark artifacts are written.",
    )
    real_benchmark_eval_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    real_benchmark_eval_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )
    real_benchmark_eval_parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="SWE-bench --max_workers value for generated native launch commands.",
    )
    real_benchmark_eval_parser.add_argument(
        "--python-executable",
        default=DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
        help="Python executable prefix to include in generated SWE-bench commands.",
    )

    real_benchmark_repetitions_parser = subcommands.add_parser(
        "real-benchmark-repetitions",
        help="Run repeated real benchmark evals into child logbooks and aggregate them.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Parent directory where repeated benchmark artifacts are written.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "--repetitions",
        type=int,
        required=True,
        help="Number of sequential real benchmark eval runs to execute.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="SWE-bench --max_workers value for generated native launch commands.",
    )
    real_benchmark_repetitions_parser.add_argument(
        "--python-executable",
        default=DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
        help="Python executable prefix to include in generated SWE-bench commands.",
    )

    real_smoke_runbook_parser = subcommands.add_parser(
        "real-smoke-runbook",
        help="Write commands and expected artifacts for a real smoke run.",
    )
    real_smoke_runbook_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    real_smoke_runbook_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where the runbook artifact is written.",
    )
    real_smoke_runbook_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used in generated commands.",
    )
    real_smoke_runbook_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format to print. The persisted runbook artifact is always JSON.",
    )

    real_benchmark_runbook_parser = subcommands.add_parser(
        "real-benchmark-runbook",
        help="Write commands and expected artifacts for a real benchmark run.",
    )
    real_benchmark_runbook_parser.add_argument(
        "config",
        type=Path,
        help="Path to a regatta TOML file.",
    )
    real_benchmark_runbook_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where the runbook artifact is written.",
    )
    real_benchmark_runbook_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used in generated commands.",
    )
    real_benchmark_runbook_parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="SWE-bench --max_workers value for generated native launch commands.",
    )
    real_benchmark_runbook_parser.add_argument(
        "--python-executable",
        default=DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
        help="Python executable prefix to include in generated SWE-bench commands.",
    )
    real_benchmark_runbook_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format to print. The persisted runbook artifact is always JSON.",
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

    if args.command == "runtime-instances":
        try:
            if args.write_logbook:
                plan = write_runtime_instances_plan(
                    args.config,
                    args.logbook,
                    args.workspace,
                )
            else:
                plan = build_runtime_instances_plan(
                    args.config,
                    args.logbook,
                    args.workspace,
                )
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

    if args.command == "predictions-from-attempts":
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

    if args.command == "benchmark-report":
        try:
            report = render_benchmark_report(
                args.logbook,
                args.format,
                vessel_name=args.vessel,
                task_id=args.task,
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            return 0
        print(report, end="")
        return 0

    if args.command == "benchmark-aggregate":
        try:
            report = render_benchmark_aggregate(args.logbook, args.format)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            return 0
        print(report, end="")
        return 0

    if args.command == "benchmark-status":
        report = render_benchmark_status(args.logbook, args.format)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            return 0
        print(report, end="")
        return 0

    if args.command == "benchmark-plan":
        try:
            plan = write_benchmark_execution_plan(args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(plan, indent=2))
        return 0

    if args.command == "benchmark-readiness-report":
        try:
            report = render_benchmark_readiness_report(args.logbook, args.format)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            return 0
        print(report, end="")
        return 0

    if args.command == "readiness-gate":
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
                "readiness gate blocked: "
                f"{gate.blocked_vessel_count} blocked vessel(s)",
                file=sys.stderr,
            )
        return gate.exit_code

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

    if args.command == "benchmark-launch":
        try:
            launch_result = write_benchmark_launch_result(logbook_dir=args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(launch_result, indent=2))
        return 0 if launch_result["status"] in {"complete", "partial"} else 1

    if args.command == "benchmark-collect-grading":
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

    if args.command == "preflight-report":
        try:
            report = write_preflight_evidence_report(args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "smoke-readiness-report":
        try:
            report = write_smoke_readiness_report(args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "ready" else 1

    if args.command == "smoke-report":
        try:
            report = render_smoke_report(args.logbook, args.format)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            return 0
        print(report, end="")
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

    if args.command == "task-attempts":
        try:
            summary = run_task_attempts(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                secret_values=parse_secret_values(args.secret),
                agent_name=args.agent,
                task_agent=_task_attempt_agent(args.agent),
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] == "completed" else 1

    if args.command == "task-attempt-scorecard":
        try:
            scorecard = write_task_attempt_scorecard(args.logbook)
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(scorecard, indent=2))
        return 0 if scorecard["status"] == "complete" else 1

    if args.command == "local-smoke-eval":
        try:
            summary = run_local_smoke_eval(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                secret_values=parse_secret_values(args.secret),
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] == "complete" else 1

    if args.command == "pi-smoke-eval":
        try:
            summary = run_pi_smoke_eval(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                secret_values=parse_secret_values(args.secret),
                task_agent=_task_attempt_agent("pi"),
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] == "complete" else 1

    if args.command == "real-smoke-eval":
        try:
            summary = run_real_smoke_eval(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                secret_values=parse_secret_values(args.secret),
                agent_prompt_runner_factory=_agent_prompt_runner_factory("pi"),
                task_agent=_task_attempt_agent("pi"),
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] == "ready" else 1

    if args.command == "real-benchmark-eval":
        try:
            summary = run_real_benchmark_eval(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                secret_values=parse_secret_values(args.secret),
                agent_prompt_runner_factory=_agent_prompt_runner_factory("pi"),
                task_agent=_task_attempt_agent("pi"),
                max_workers=args.max_workers,
                python_executable=args.python_executable,
                progress=_stderr_progress,
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] in {"complete", "partial"} else 1

    if args.command == "real-benchmark-repetitions":
        try:
            summary = run_real_benchmark_repetitions(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                secret_values=parse_secret_values(args.secret),
                repetitions=args.repetitions,
                agent_prompt_runner_factory=_agent_prompt_runner_factory("pi"),
                task_agent=_task_attempt_agent("pi"),
                max_workers=args.max_workers,
                python_executable=args.python_executable,
                progress=_stderr_progress,
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2))
        return 0 if summary["status"] in {"complete", "partial"} else 1

    if args.command == "real-smoke-runbook":
        try:
            runbook = write_real_smoke_runbook(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.format == "markdown":
            print(render_real_smoke_runbook(runbook), end="")
        else:
            print(json.dumps(runbook, indent=2))
        return 0

    if args.command == "real-benchmark-runbook":
        try:
            runbook = write_real_benchmark_runbook(
                config_path=args.config,
                logbook_dir=args.logbook,
                workspace_path=args.workspace,
                max_workers=args.max_workers,
                python_executable=args.python_executable,
            )
        except ConfigError as error:
            print(f"error: invalid regatta config: {error}", file=sys.stderr)
            return 1
        if args.format == "markdown":
            print(render_real_benchmark_runbook(runbook), end="")
        else:
            print(json.dumps(runbook, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2))


def _stderr_progress(message: str) -> None:
    print(f"yacht: {message}", file=sys.stderr, flush=True)


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


def _task_attempt_agent(agent_name: str) -> TaskAgent | None:
    if agent_name == "local-smoke":
        return None
    if agent_name == "pi":
        return PiAdapter(task_launcher=SubprocessPiTaskLauncher())
    raise ConfigError(f"unsupported task attempt agent {agent_name}")
