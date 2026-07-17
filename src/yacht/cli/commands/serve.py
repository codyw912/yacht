from __future__ import annotations

import argparse
from pathlib import Path

from yacht.serve.server import DEFAULT_HOST, DEFAULT_PORT, run_server


def register(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "serve",
        help="Serve a local read-only dashboard over a directory of logbooks.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help=(
            "Directory to scan for logbooks (the directory itself and one "
            "level of subdirectories). Defaults to the current directory."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Address to bind. Defaults to localhost; the dashboard is a "
        "single-user inspection tool, not a deployment target.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind (default {DEFAULT_PORT}).",
    )
    parser.set_defaults(handler=_serve)


def _serve(args: argparse.Namespace) -> int:
    return run_server(root=args.root, host=args.host, port=args.port)
