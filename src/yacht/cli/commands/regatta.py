from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.cli import output
from yacht.config.agent_selection import configured_harness_declarations
from yacht.config.agent_selection import configured_harness_name
from yacht.config.loader import load_regatta
from yacht.courses.registry import course_adapter
from yacht.domain.model import ConfigError, run_regatta
from yacht.harnesses.registry import agent_prompt_runner_factory
from yacht.harnesses.registry import task_agent
from yacht.reports.surface_metadata import regatta_surfaces_to_json
from yacht.preflight.runner import parse_secret_values
from yacht.workflows.real_benchmark_eval import run_real_benchmark_eval
from yacht.workflows.real_benchmark_repetitions import run_real_benchmark_repetitions
from yacht.workflows.real_benchmark_runbook import write_real_benchmark_runbook
from yacht.workflows.real_benchmark_summary import render_real_benchmark_eval_summary
from yacht.workflows.real_benchmark_summary import (
    render_real_benchmark_repetitions_summary,
)
from yacht.workflows.real_smoke_eval import run_real_smoke_eval
from yacht.workflows.real_smoke_runbook import write_real_smoke_runbook


def register(subcommands: argparse._SubParsersAction) -> None:
    run_parser = subcommands.add_parser(
        "run",
        help=(
            "Run a regatta config end to end: preflight, task attempts, "
            "grading, and scorecard."
        ),
    )
    run_parser.add_argument("config", type=Path, help="Path to a regatta TOML file.")
    run_parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Directory where run artifacts and scorecards are written.",
    )
    run_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace path used as the prepared runtime working directory.",
    )
    run_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicit secret value to inject for a configured secret reference.",
    )
    run_parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Run the benchmark this many times and aggregate the results.",
    )
    run_parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="SWE-bench --max_workers value for generated native launch commands.",
    )
    run_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the completion summary.",
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


def _run(args: argparse.Namespace) -> int:
    try:
        regatta = load_regatta(args.config)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1

    if regatta.course.adapter is None and not regatta.runtime_recipes:
        return _run_mock_course(args)
    if regatta.course.adapter is None:
        if args.repetitions != 1:
            print(
                "error: --repetitions requires a course adapter; "
                f"{regatta.course.name} is a smoke course",
                file=sys.stderr,
            )
            return 1
        return _run_smoke(args)
    if args.repetitions != 1:
        return _run_benchmark_repetitions(args)
    return _run_benchmark(args)


def _run_mock_course(args: argparse.Namespace) -> int:
    try:
        scorecard = run_regatta(args.config, args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(scorecard, indent=2))
    return 0


def _run_smoke(args: argparse.Namespace) -> int:
    try:
        agent_name = configured_harness_name(args.config)
        harness_declarations = configured_harness_declarations(args.config)
        write_real_smoke_runbook(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
        )
        summary = run_real_smoke_eval(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            agent_prompt_runner_factory=agent_prompt_runner_factory(
                agent_name, harness_declarations
            ),
            task_agent=task_agent(agent_name, harness_declarations),
            agent_name=agent_name,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ready" else 1


def _run_benchmark(args: argparse.Namespace) -> int:
    try:
        agent_name, prompt_factory, bound_task_agent = _eval_binding(args.config)
        write_real_benchmark_runbook(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            max_workers=args.max_workers,
        )
        summary = run_real_benchmark_eval(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            agent_prompt_runner_factory=prompt_factory,
            task_agent=bound_task_agent,
            agent_name=agent_name,
            max_workers=args.max_workers,
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


def _run_benchmark_repetitions(args: argparse.Namespace) -> int:
    try:
        agent_name, prompt_factory, bound_task_agent = _eval_binding(args.config)
        summary = run_real_benchmark_repetitions(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            repetitions=args.repetitions,
            agent_name=agent_name,
            agent_prompt_runner_factory=prompt_factory,
            task_agent=bound_task_agent,
            max_workers=args.max_workers,
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


def _eval_binding(config_path: Path):
    """Host adapters need one harness. Harbor native rollout does not."""
    regatta = load_regatta(config_path)
    declarations = configured_harness_declarations(config_path)
    if regatta.course.adapter is not None:
        adapter = course_adapter(regatta.course.adapter.kind)
        if adapter.native_rollout and regatta.course.adapter.harness == "harbor":
            names = tuple(regatta_surfaces_to_json(regatta).get("agent_harnesses", ()))
            if not names:
                raise ConfigError(
                    "real benchmark commands require at least one configured "
                    "agent harness; found none"
                )
            return ", ".join(str(name) for name in names), None, None
    name = configured_harness_name(config_path)
    return (
        name,
        agent_prompt_runner_factory(name, declarations),
        task_agent(name, declarations),
    )
