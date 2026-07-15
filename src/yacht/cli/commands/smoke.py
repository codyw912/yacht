from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.cli import output
from yacht.config.agent_selection import configured_harness_name
from yacht.domain.model import ConfigError
from yacht.harnesses.registry import agent_prompt_runner_factory
from yacht.harnesses.registry import task_agent
from yacht.preflight.runner import parse_secret_values
from yacht.reports.smoke_readiness import write_smoke_readiness_report
from yacht.reports.smoke_report import render_smoke_report
from yacht.workflows.local_smoke_eval import run_local_smoke_eval
from yacht.workflows.pi_smoke_eval import run_pi_smoke_eval
from yacht.workflows.real_smoke_eval import run_real_smoke_eval
from yacht.workflows.real_smoke_runbook import render_real_smoke_runbook
from yacht.workflows.real_smoke_runbook import write_real_smoke_runbook


def register(subcommands: argparse._SubParsersAction) -> None:
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
    local_smoke_eval_parser.set_defaults(handler=_local_smoke_eval)

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
    pi_smoke_eval_parser.set_defaults(handler=_pi_smoke_eval)

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
    real_smoke_eval_parser.set_defaults(handler=_real_smoke_eval)

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
    smoke_readiness_report_parser.set_defaults(handler=_smoke_readiness_report)

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
    smoke_report_parser.set_defaults(handler=_smoke_report)

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
    real_smoke_runbook_parser.set_defaults(handler=_real_smoke_runbook)


def _local_smoke_eval(args: argparse.Namespace) -> int:
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


def _pi_smoke_eval(args: argparse.Namespace) -> int:
    try:
        summary = run_pi_smoke_eval(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            task_agent=task_agent("pi"),
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "complete" else 1


def _real_smoke_eval(args: argparse.Namespace) -> int:
    try:
        agent_name = configured_harness_name(
            args.config,
            command_label="real smoke eval commands",
        )
        summary = run_real_smoke_eval(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=parse_secret_values(args.secret),
            agent_prompt_runner_factory=agent_prompt_runner_factory(agent_name),
            task_agent=task_agent(agent_name),
            agent_name=agent_name,
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ready" else 1


def _smoke_readiness_report(args: argparse.Namespace) -> int:
    try:
        report = write_smoke_readiness_report(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ready" else 1


def _smoke_report(args: argparse.Namespace) -> int:
    try:
        report = render_smoke_report(args.logbook, args.format)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    return output.emit_report(report, args.output)


def _real_smoke_runbook(args: argparse.Namespace) -> int:
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
