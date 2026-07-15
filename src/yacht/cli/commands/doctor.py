from __future__ import annotations

import argparse
from pathlib import Path

from yacht.workflows.doctor import render_doctor_report, run_doctor


def register(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "doctor",
        help="Check host prerequisites for running YACHT evals.",
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        help=(
            "Optional regatta TOML file. When given, doctor also checks the "
            "config, its container runtime images, and its env secrets."
        ),
    )
    parser.add_argument(
        "--logbook",
        type=Path,
        default=Path("logbook"),
        help="Logbook directory to check for writability.",
    )
    parser.add_argument(
        "--skip-swebench",
        action="store_true",
        help="Skip resolving the native SWE-bench harness (avoids network use).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the doctor report.",
    )
    parser.set_defaults(handler=_doctor)


def _doctor(args: argparse.Namespace) -> int:
    report = run_doctor(
        config_path=args.config,
        logbook_dir=args.logbook,
        check_swebench=not args.skip_swebench,
    )
    print(render_doctor_report(report, args.format), end="")
    return 0 if report["status"] == "passed" else 1
