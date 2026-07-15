from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.logbook.index import RUN_INDEX_PATH
from yacht.logbook.io import load_json_object
from yacht.reports.smoke_readiness import SMOKE_READINESS_REPORT_PATH
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH
from yacht.workflows.real_smoke_runbook import REAL_SMOKE_RUNBOOK_PATH

_SMOKE_ARTIFACTS = (
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
    artifacts = [
        {
            "name": name,
            "path": str(logbook_dir / path),
            "present": (logbook_dir / path).exists(),
        }
        for name, path in _SMOKE_ARTIFACTS
    ]
    readiness_path = logbook_dir / SMOKE_READINESS_REPORT_PATH
    readiness_status = None
    if readiness_path.exists():
        readiness = load_json_object(readiness_path, "smoke readiness report artifact")
        readiness_status = str(readiness.get("status"))
    missing = [artifact["name"] for artifact in artifacts if not artifact["present"]]
    if missing:
        next_step = f"uv run yacht run <config> --logbook {logbook_dir}"
    else:
        next_step = f"uv run yacht report --logbook {logbook_dir}"
    return {
        "run_kind": "real-smoke",
        "logbook": str(logbook_dir),
        "status": readiness_status or ("missing" if missing else "unknown"),
        "artifacts": artifacts,
        "missing": missing,
        "next_step": next_step,
    }


def _render_text(status: dict[str, Any]) -> str:
    lines = [
        f"Smoke logbook: {status['logbook']}",
        f"Status: {status['status']}",
    ]
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
        "| Artifact | Present | Path |",
        "| -------- | ------- | ---- |",
    ]
    for artifact in status["artifacts"]:
        present = "yes" if artifact["present"] else "no"
        lines.append(f"| {artifact['name']} | {present} | `{artifact['path']}` |")
    lines.extend(["", f"Next: `{status['next_step']}`"])
    return "\n".join(lines) + "\n"
