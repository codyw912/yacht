from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from yacht.logbook.index import RUN_INDEX_PATH, read_run_kind
from yacht.reports.benchmark_aggregate import BENCHMARK_AGGREGATE_PATH
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.reports.next_steps import command_step
from yacht.workflows.real_benchmark_eval import REAL_BENCHMARK_EVAL_PATH
from yacht.workflows.real_benchmark_repetitions import REAL_BENCHMARK_REPETITIONS_PATH
from yacht.domain.model import ConfigError


LATEST_LOGBOOK_SCHEMA = "yacht.latest-logbook.v1"


_BENCHMARK_ARTIFACTS = {
    "real_benchmark_eval": REAL_BENCHMARK_EVAL_PATH,
    "real_benchmark_repetitions": REAL_BENCHMARK_REPETITIONS_PATH,
    "benchmark_scorecard": BENCHMARK_SCORECARD_PATH,
    "benchmark_aggregate": BENCHMARK_AGGREGATE_PATH,
    "run_index": RUN_INDEX_PATH,
}


def build_latest_logbook(root: Path, *, prefix: str = "yacht-") -> dict[str, Any]:
    if not root.exists():
        raise ConfigError(f"latest logbook root not found: {root}")
    if not root.is_dir():
        raise ConfigError(f"latest logbook root is not a directory: {root}")

    candidates = _candidate_logbooks(root, prefix=prefix)
    if not candidates:
        detail = f" under {root}"
        if prefix:
            detail += f" with prefix {prefix!r}"
        raise ConfigError(f"no YACHT benchmark logbooks found{detail}")

    latest = max(
        candidates,
        key=lambda candidate: (
            float(candidate["updated_timestamp"]),
            str(candidate["logbook"]),
        ),
    )
    return {
        "schema": LATEST_LOGBOOK_SCHEMA,
        "status": "found",
        "root": str(root),
        "prefix": prefix,
        "logbook": latest["logbook"],
        "kind": latest["kind"],
        "updated_at": latest["updated_at"],
        "artifacts": latest["artifacts"],
        "next_steps": _next_steps(Path(str(latest["logbook"]))),
    }


def render_latest_logbook(
    root: Path,
    *,
    prefix: str = "yacht-",
    output_format: str = "text",
) -> str:
    report = build_latest_logbook(root, prefix=prefix)
    if output_format == "json":
        return json.dumps(report, indent=2) + "\n"
    return _render_text(report)


def _candidate_logbooks(root: Path, *, prefix: str) -> list[dict[str, Any]]:
    candidates = []
    root_candidate = _candidate_logbook(root)
    if root_candidate is not None:
        candidates.append(root_candidate)
    try:
        children = list(root.iterdir())
    except OSError as error:
        raise ConfigError(
            f"could not scan latest logbook root {root}: {error}"
        ) from error
    for child in children:
        if not child.is_dir():
            continue
        if prefix and not child.name.startswith(prefix):
            continue
        candidate = _candidate_logbook(child)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_logbook(logbook: Path) -> dict[str, Any] | None:
    present = {
        name: logbook / relative_path
        for name, relative_path in _BENCHMARK_ARTIFACTS.items()
        if (logbook / relative_path).is_file()
    }
    if not present:
        return None
    updated_timestamp = max(path.stat().st_mtime for path in present.values())
    return {
        "logbook": str(logbook),
        "kind": _logbook_kind(present),
        "updated_timestamp": updated_timestamp,
        "updated_at": datetime.fromtimestamp(updated_timestamp).isoformat(
            timespec="seconds"
        ),
        "artifacts": {name: str(path) for name, path in present.items()},
    }


def _logbook_kind(present: dict[str, Path]) -> str:
    if "real_benchmark_repetitions" in present or "benchmark_aggregate" in present:
        return "benchmark-repetitions"
    if set(present) == {"run_index"}:
        run_kind = read_run_kind(present["run_index"].parent)
        if run_kind is not None:
            return run_kind
    return "benchmark"


def _next_steps(logbook: Path) -> list[dict[str, object]]:
    return [
        command_step(
            label="Inspect benchmark status",
            reason="Show artifact readiness and the next recommended command.",
            command=[
                "uv",
                "run",
                "yacht",
                "benchmark-status",
                "--logbook",
                str(logbook),
            ],
        ),
        command_step(
            label="Render benchmark report",
            reason="Show benchmark outcomes, usage, and artifact paths.",
            command=[
                "uv",
                "run",
                "yacht",
                "benchmark-report",
                "--logbook",
                str(logbook),
            ],
        ),
    ]


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Latest logbook: {report['logbook']}",
        f"Kind: {report['kind']}",
        f"Updated: {report['updated_at']}",
        f"Root: {report['root']}",
    ]
    artifacts = report.get("artifacts")
    if isinstance(artifacts, dict) and artifacts:
        lines.extend(["", "Artifacts:"])
        lines.extend(f"- {name}: {path}" for name, path in artifacts.items())
    lines.extend(["", "Next steps:"])
    lines.extend(_next_step_lines(report.get("next_steps")))
    return "\n".join(lines) + "\n"


def _next_step_lines(steps: Any) -> list[str]:
    if not isinstance(steps, list) or not steps:
        return ["- none"]
    lines = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        lines.append(f"{index}. {step.get('label', 'Next step')}")
        command = step.get("command_preview")
        if isinstance(command, str):
            lines.append(f"   command: {command}")
        reason = step.get("reason")
        if isinstance(reason, str):
            lines.append(f"   reason: {reason}")
    return lines
