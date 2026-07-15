from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from yacht.cli import output
from yacht.config.agent_selection import configured_harness_name
from yacht.config.loader import load_regatta
from yacht.domain.model import ConfigError
from yacht.harnesses.registry import agent_prompt_runner_factory
from yacht.harnesses.registry import task_agent
from yacht.preflight.runner import parse_secret_values
from yacht.workflows.benchmark_launcher_handoff import (
    DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
)
from yacht.workflows.real_benchmark_eval import run_real_benchmark_eval
from yacht.workflows.real_benchmark_repetitions import run_real_benchmark_repetitions
from yacht.workflows.real_benchmark_runbook import render_real_benchmark_runbook
from yacht.workflows.real_benchmark_runbook import write_real_benchmark_runbook
from yacht.workflows.real_benchmark_summary import render_real_benchmark_eval_summary
from yacht.workflows.real_benchmark_summary import (
    render_real_benchmark_repetitions_summary,
)


def register(subcommands: argparse._SubParsersAction) -> None:
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
    real_benchmark_eval_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the completion summary.",
    )
    real_benchmark_eval_parser.set_defaults(handler=_real_benchmark_eval)

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
        default=None,
        help=(
            "Parent directory where repeated benchmark artifacts are written. "
            "Defaults to a timestamped directory under the system temp directory."
        ),
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
    real_benchmark_repetitions_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the completion summary.",
    )
    real_benchmark_repetitions_parser.set_defaults(handler=_real_benchmark_repetitions)

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
    real_benchmark_runbook_parser.set_defaults(handler=_real_benchmark_runbook)


def _real_benchmark_eval(args: argparse.Namespace) -> int:
    try:
        agent_name = configured_harness_name(args.config)
        summary = run_real_benchmark_eval(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            agent_prompt_runner_factory=agent_prompt_runner_factory(agent_name),
            task_agent=task_agent(agent_name),
            agent_name=agent_name,
            max_workers=args.max_workers,
            python_executable=args.python_executable,
            progress=output.stderr_progress,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print(render_real_benchmark_eval_summary(summary), end="")
    return 0 if summary["status"] in {"complete", "partial"} else 1


def _real_benchmark_repetitions(args: argparse.Namespace) -> int:
    try:
        agent_name = configured_harness_name(args.config)
        summary = run_real_benchmark_repetitions(
            config_path=args.config,
            logbook_dir=args.logbook
            or _default_repeated_benchmark_logbook(args.config),
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            repetitions=args.repetitions,
            agent_name=agent_name,
            agent_prompt_runner_factory=agent_prompt_runner_factory(agent_name),
            task_agent=task_agent(agent_name),
            max_workers=args.max_workers,
            python_executable=args.python_executable,
            progress=output.stderr_progress,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print(render_real_benchmark_repetitions_summary(summary), end="")
    return 0 if summary["status"] in {"complete", "partial"} else 1


def _real_benchmark_runbook(args: argparse.Namespace) -> int:
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


def _default_repeated_benchmark_logbook(config_path: Path) -> Path:
    regatta = load_regatta(config_path)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return Path(tempfile.gettempdir()) / f"yacht-{_path_slug(regatta.name)}-{timestamp}"


def _path_slug(value: str) -> str:
    slug = "".join(character if character.isalnum() else "-" for character in value)
    return "-".join(part for part in slug.lower().split("-") if part) or "benchmark"
