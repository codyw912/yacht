from __future__ import annotations

import argparse

from yacht.cli.commands import artifacts
from yacht.cli.commands import attempts
from yacht.cli.commands import benchmark
from yacht.cli.commands import preflight
from yacht.cli.commands import runtimes
from yacht.cli.commands import smoke

INTERNAL_MODULES = (
    runtimes,
    artifacts,
    benchmark,
    preflight,
    attempts,
    smoke,
)


def register(subcommands: argparse._SubParsersAction) -> None:
    internals_parser = subcommands.add_parser(
        "internals",
        help="Pipeline stage commands for debugging and incremental runs.",
    )
    internal_subcommands = internals_parser.add_subparsers(
        dest="internal_command",
        required=True,
    )
    for module in INTERNAL_MODULES:
        module.register(internal_subcommands)
