from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.domain.model import ConfigError
from yacht.reports.smoke_readiness import write_smoke_readiness_report


def register(subcommands: argparse._SubParsersAction) -> None:
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


def _smoke_readiness_report(args: argparse.Namespace) -> int:
    try:
        report = write_smoke_readiness_report(args.logbook)
    except ConfigError as error:
        print(f"error: invalid regatta config: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ready" else 1
