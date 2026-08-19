from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError
from yacht.logbook.index import (
    RUN_INDEX_PATH,
    LogbookSnapshot,
    LogbookState,
    is_logbook_candidate,
    read_logbook,
)
from yacht.reports.next_steps import command_step


LATEST_LOGBOOK_SCHEMA = "yacht.latest-logbook.v1"


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
    if not is_logbook_candidate(logbook):
        return None
    snapshot = read_logbook(logbook)
    present = {
        artifact.name: str(artifact.path)
        for artifact in snapshot.artifacts
        if artifact.present
    }
    index_path = logbook / RUN_INDEX_PATH
    if index_path.is_file():
        present["run_index"] = str(index_path)
    updated_timestamp = _updated_timestamp(snapshot, index_path)
    return {
        "logbook": str(logbook),
        "kind": _logbook_kind(snapshot),
        "updated_timestamp": updated_timestamp,
        "updated_at": datetime.fromtimestamp(updated_timestamp).isoformat(
            timespec="seconds"
        ),
        "artifacts": present,
    }


def _updated_timestamp(snapshot: LogbookSnapshot, index_path: Path) -> float:
    if snapshot.updated_at is not None:
        return datetime.fromisoformat(
            snapshot.updated_at.replace("Z", "+00:00")
        ).timestamp()
    if index_path.exists() or index_path.is_symlink():
        return index_path.lstat().st_mtime
    return snapshot.logbook.stat().st_mtime


def _logbook_kind(snapshot: LogbookSnapshot) -> str:
    artifact_names = {artifact.name for artifact in snapshot.artifacts}
    if artifact_names & {"real_benchmark_repetitions", "benchmark_aggregate"}:
        return "benchmark-repetitions"
    if snapshot.state is LogbookState.BROKEN:
        return "broken"
    if snapshot.run_kind == "real-benchmark":
        return "benchmark"
    return snapshot.run_kind or "benchmark"


def _next_steps(logbook: Path) -> list[dict[str, object]]:
    return [
        command_step(
            label="Inspect benchmark status",
            reason="Show artifact readiness and the next recommended command.",
            command=[
                "uv",
                "run",
                "yacht",
                "status",
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
                "report",
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
