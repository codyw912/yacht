from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.cli import output
from yacht.domain.model import ConfigError
from yacht.harnesses.registry import agent_prompt_runner_factory
from yacht.config.agent_selection import configured_harness_declarations
from yacht.harnesses.registry import supported_agent_preflight_names
from yacht.preflight.runner import (
    build_preflight_execution_plan,
    parse_secret_values,
    run_preflight,
)
from yacht.reports.preflight_evidence import render_preflight_evidence_report
from yacht.reports.preflight_evidence import write_preflight_evidence_report


def register(subcommands: argparse._SubParsersAction) -> None:
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
    preflight_report_parser.add_argument(
        "--format",
        choices=("json", "text", "markdown"),
        default="json",
        help="Output format for the preflight evidence report.",
    )
    preflight_report_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered preflight report.",
    )
    preflight_report_parser.set_defaults(handler=_preflight_report)

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
        default="none",
        help=(
            "Opt into agent-prompt preflight checks with the selected adapter: "
            f"{', '.join(supported_agent_preflight_names())}, or a harness "
            "declared in the config."
        ),
    )
    preflight_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved preflight execution plan without running checks.",
    )
    preflight_parser.set_defaults(handler=_preflight)


def _preflight_report(args: argparse.Namespace) -> int:
    try:
        report = write_preflight_evidence_report(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    rendered = render_preflight_evidence_report(report, args.format)
    return output.emit_report(rendered, args.output)


def _declarations(args: argparse.Namespace):
    if args.agent_preflight in supported_agent_preflight_names():
        return None
    return configured_harness_declarations(args.config)


def _preflight(args: argparse.Namespace) -> int:
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
            agent_prompt_runner_factory=agent_prompt_runner_factory(
                args.agent_preflight,
                _declarations(args),
            ),
        )
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "passed" else 1
