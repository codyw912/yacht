from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.domain.model import ConfigError
from yacht.config.agent_selection import configured_harness_declarations
from yacht.harnesses.registry import supported_task_attempt_names
from yacht.harnesses.registry import task_agent
from yacht.secret_resolution import resolve_secret_arguments
from yacht.reports.task_attempt_scorecard import write_task_attempt_scorecard
from yacht.workflows.task_attempt_runner import run_task_attempts


def register(subcommands: argparse._SubParsersAction) -> None:
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
        help=(
            "Task attempt agent adapter to launch: "
            f"{', '.join(supported_task_attempt_names())}, or a harness "
            "declared in the config."
        ),
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
    task_attempts_parser.set_defaults(handler=_task_attempts)

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
    task_attempt_scorecard_parser.set_defaults(handler=_task_attempt_scorecard)


def _declarations(args: argparse.Namespace):
    if args.agent in supported_task_attempt_names():
        return None
    return configured_harness_declarations(args.config)


def _task_attempts(args: argparse.Namespace) -> int:
    try:
        summary = run_task_attempts(
            config_path=args.config,
            logbook_dir=args.logbook,
            workspace_path=args.workspace,
            secret_values=resolve_secret_arguments(args.secret),
            agent_name=args.agent,
            task_agent=task_agent(args.agent, _declarations(args)),
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "completed" else 1


def _task_attempt_scorecard(args: argparse.Namespace) -> int:
    try:
        scorecard = write_task_attempt_scorecard(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(scorecard, indent=2))
    return 0 if scorecard["status"] == "complete" else 1
