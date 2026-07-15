from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yacht.domain.model import ConfigError
from yacht.runtimes.instances import build_runtime_instances_plan
from yacht.runtimes.instances import write_runtime_instances_plan


def register(subcommands: argparse._SubParsersAction) -> None:
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
    runtime_instances_parser.set_defaults(handler=_runtime_instances)


def _runtime_instances(args: argparse.Namespace) -> int:
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
