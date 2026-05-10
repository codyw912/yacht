from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from yacht.pi_adapter import PiAdapter, SubprocessPiPromptLauncher
from yacht.preflight_runner import (
    AgentPromptRunnerFactory,
    parse_secret_values,
    run_preflight,
)
from yacht.regatta import ConfigError, load_regatta, run_regatta
from yacht.runtime_plan import build_runtime_plan


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
        choices=("none", "pi"),
        default="none",
        help="Opt into agent-prompt preflight checks with the selected adapter.",
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

    if args.command == "preflight":
        try:
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
    raise ConfigError(f"unsupported agent preflight adapter {adapter_name}")
