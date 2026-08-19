from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.logbook.index import (
    RUN_INDEX_PATH,
    LogbookSnapshot,
    LogbookState,
    is_logbook_candidate,
    require_logbook,
)
from yacht.logbook.io import load_json_object
from yacht.reports.smoke_readiness import SMOKE_READINESS_REPORT_PATH
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH
from yacht.workflows.real_smoke_runbook import REAL_SMOKE_RUNBOOK_PATH

_EXPECTED_SMOKE_ARTIFACTS = (
    ("run-index", RUN_INDEX_PATH),
    ("real-smoke-runbook", REAL_SMOKE_RUNBOOK_PATH),
    ("smoke-readiness-report", SMOKE_READINESS_REPORT_PATH),
    ("task-attempt-scorecard", TASK_ATTEMPT_SCORECARD_PATH),
)


def render_smoke_status(logbook_dir: Path, output_format: str = "text") -> str:
    status = build_smoke_status(logbook_dir)
    if output_format == "json":
        return json.dumps(status, indent=2) + "\n"
    if output_format == "markdown":
        return _render_markdown(status)
    return _render_text(status)


def build_smoke_status(logbook_dir: Path) -> dict[str, Any]:
    if not is_logbook_candidate(logbook_dir):
        return _missing_smoke_status(logbook_dir)
    snapshot = require_logbook(logbook_dir)
    artifacts = _artifact_statuses(snapshot)
    readiness_status = None
    readiness = snapshot.artifact("smoke_readiness_report")
    if readiness is not None and readiness.file_present:
        readiness_payload = load_json_object(
            readiness.path,
            "smoke readiness report artifact",
        )
        readiness_status = str(readiness_payload.get("status"))
    lifecycle_status = snapshot.status
    missing = [artifact["name"] for artifact in artifacts if not artifact["present"]]
    if missing:
        next_step = f"uv run yacht run <config> --logbook {logbook_dir}"
    else:
        next_step = f"uv run yacht report --logbook {logbook_dir}"
    return {
        "run_kind": snapshot.run_kind,
        "logbook": str(logbook_dir),
        "status": readiness_status or snapshot.status or "unknown",
        "lifecycle_status": lifecycle_status,
        "readiness_status": readiness_status,
        "artifacts": artifacts,
        "missing": missing,
        "next_step": next_step,
    }


def _missing_smoke_status(logbook_dir: Path) -> dict[str, Any]:
    artifacts = [
        {
            "name": name,
            "path": str(logbook_dir / path),
            "present": False,
        }
        for name, path in _EXPECTED_SMOKE_ARTIFACTS
    ]
    return {
        "run_kind": "real-smoke",
        "logbook": str(logbook_dir),
        "lifecycle_status": None,
        "readiness_status": None,
        "status": "missing",
        "artifacts": artifacts,
        "missing": [str(artifact["name"]) for artifact in artifacts],
        "next_step": f"uv run yacht run <config> --logbook {logbook_dir}",
    }


def _artifact_statuses(snapshot: LogbookSnapshot) -> list[dict[str, Any]]:
    if snapshot.state is LogbookState.LEGACY_SCORECARD_ONLY:
        return [
            {
                "name": name,
                "path": str(snapshot.logbook / path),
                "present": (snapshot.logbook / path).is_file(),
            }
            for name, path in _EXPECTED_SMOKE_ARTIFACTS
        ]
    artifacts = [
        {
            "name": artifact.name.replace("_", "-"),
            "path": str(artifact.path),
            "present": artifact.present,
        }
        for artifact in snapshot.artifacts
    ]
    index_path = snapshot.logbook / RUN_INDEX_PATH
    if index_path.is_file():
        artifacts.insert(
            0,
            {
                "name": "run-index",
                "path": str(index_path),
                "present": True,
            },
        )
    return artifacts


def _render_text(status: dict[str, Any]) -> str:
    lines = [
        f"Smoke logbook: {status['logbook']}",
        f"Status: {status['status']}",
    ]
    if status.get("lifecycle_status") is not None:
        lines.append(f"Lifecycle: {status['lifecycle_status']}")
    for artifact in status["artifacts"]:
        marker = "present" if artifact["present"] else "missing"
        lines.append(f"[{marker}] {artifact['name']}: {artifact['path']}")
    lines.append(f"Next: {status['next_step']}")
    return "\n".join(lines) + "\n"


def _render_markdown(status: dict[str, Any]) -> str:
    lines = [
        f"# Smoke Logbook Status: {status['status']}",
        "",
        f"Logbook: `{status['logbook']}`",
        "",
    ]
    if status.get("lifecycle_status") is not None:
        lines.extend(
            [
                f"Lifecycle: `{status['lifecycle_status']}`",
                f"Readiness: `{status['readiness_status'] or 'unavailable'}`",
                "",
            ]
        )
    lines.extend(
        [
            "| Artifact | Present | Path |",
            "| -------- | ------- | ---- |",
        ]
    )
    for artifact in status["artifacts"]:
        present = "yes" if artifact["present"] else "no"
        lines.append(f"| {artifact['name']} | {present} | `{artifact['path']}` |")
    lines.extend(["", f"Next: `{status['next_step']}`"])
    return "\n".join(lines) + "\n"
