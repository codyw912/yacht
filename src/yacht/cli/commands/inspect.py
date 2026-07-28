from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from yacht.cli import output
from yacht.domain.model import ConfigError
from yacht.logbook.index import read_run_kind
from yacht.reports.benchmark_report import render_benchmark_report
from yacht.reports.benchmark_status import render_benchmark_status
from yacht.reports.latest_logbook import build_latest_logbook
from yacht.reports.smoke_readiness import SMOKE_READINESS_REPORT_PATH
from yacht.reports.html_report import render_smoke_html
from yacht.reports.smoke_report import render_smoke_report
from yacht.reports.smoke_status import build_smoke_status, render_smoke_status


def register(subcommands: argparse._SubParsersAction) -> None:
    status_parser = subcommands.add_parser(
        "status",
        help="Show run state and next steps for a logbook.",
    )
    status_parser.add_argument(
        "--logbook",
        type=Path,
        default=None,
        help=(
            "Logbook directory to inspect. Defaults to ./logbook, then the "
            "most recent yacht logbook in the system temp directory."
        ),
    )
    status_parser.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="Output format for the status report.",
    )
    status_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered status report.",
    )
    status_parser.set_defaults(handler=_status)

    report_parser = subcommands.add_parser(
        "report",
        help="Render the report for a smoke or benchmark logbook.",
    )
    report_parser.add_argument(
        "--logbook",
        type=Path,
        default=None,
        help=(
            "Logbook directory to report on. Defaults to ./logbook, then the "
            "most recent yacht logbook in the system temp directory."
        ),
    )
    report_parser.add_argument(
        "--format",
        choices=("text", "markdown", "html", "every-eval-ever"),
        default="text",
        help=(
            "Output format for the rendered report. every-eval-ever writes "
            "one Every Eval Ever aggregate JSON and instance JSONL per "
            "vessel into the --output directory."
        ),
    )
    report_parser.add_argument(
        "--vessel",
        help="Only show per-vessel details for this vessel name (benchmark runs).",
    )
    report_parser.add_argument(
        "--task",
        help="Only show per-vessel details for this task id (benchmark runs).",
    )
    report_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered report.",
    )
    report_parser.set_defaults(handler=_report)


def _status(args: argparse.Namespace) -> int:
    try:
        logbook_dir = _resolve_logbook(args.logbook)
        if _run_kind(logbook_dir) == "smoke":
            report = render_smoke_status(logbook_dir, args.format)
        else:
            report = render_benchmark_status(logbook_dir, args.format)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return output.emit_report(report, args.output)


def _report(args: argparse.Namespace) -> int:
    try:
        logbook_dir = _resolve_logbook(args.logbook)
        if args.format == "every-eval-ever":
            return _every_eval_ever_report(logbook_dir, args.output)
        if _run_kind(logbook_dir) == "smoke":
            if args.vessel or args.task:
                raise ConfigError(
                    "--vessel and --task filters apply to benchmark logbooks; "
                    f"{logbook_dir} holds a smoke run"
                )
            if args.format == "html":
                report = render_smoke_html(
                    smoke_status=build_smoke_status(logbook_dir),
                    logbook_dir=logbook_dir,
                )
            else:
                report = render_smoke_report(logbook_dir, args.format)
        else:
            report = render_benchmark_report(
                logbook_dir,
                args.format,
                vessel_name=args.vessel,
                task_id=args.task,
            )
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return output.emit_report(report, args.output)


def _every_eval_ever_report(logbook_dir: Path, output_dir: Path | None) -> int:
    from time import time

    from yacht.reports.every_eval_ever import write_every_eval_ever_export

    if output_dir is None:
        print(
            "error: --format every-eval-ever writes a file per vessel; pass "
            "--output <directory>",
            file=sys.stderr,
        )
        return 1
    try:
        manifest = write_every_eval_ever_export(
            logbook_dir=logbook_dir,
            output_dir=output_dir,
            retrieved_timestamp=f"{time():.6f}",
        )
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for export in manifest["exports"]:
        print(
            f"{export['comparison']}/{export['vessel']}: "
            f"{export['aggregate_path']} "
            f"({export['instance_rows']} instance rows)"
        )
    return 0


def _resolve_logbook(logbook_arg: Path | None) -> Path:
    if logbook_arg is not None:
        return logbook_arg
    default = Path("logbook")
    if default.is_dir():
        return default
    latest = build_latest_logbook(Path(tempfile.gettempdir()))
    logbook_dir = Path(str(latest["logbook"]))
    print(f"yacht: using latest logbook {logbook_dir}", file=sys.stderr)
    return logbook_dir


def _run_kind(logbook_dir: Path) -> str:
    if not logbook_dir.is_dir():
        raise ConfigError(
            f"logbook directory not found: {logbook_dir}; run an eval first "
            "or pass --logbook"
        )
    kind = read_run_kind(logbook_dir)
    if kind == "real-smoke":
        return "smoke"
    if kind is not None:
        return "benchmark"
    if (logbook_dir / SMOKE_READINESS_REPORT_PATH).exists() and not (
        logbook_dir / "benchmark-scorecard.json"
    ).exists():
        return "smoke"
    return "benchmark"
