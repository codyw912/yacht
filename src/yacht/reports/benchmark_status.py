from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.logbook.index import (
    LogbookSnapshot,
    LogbookState,
    is_logbook_candidate,
    require_logbook,
)
from yacht.workflows.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.workflows.benchmark_grading_collection import (
    BENCHMARK_GRADING_COLLECTION_PATH,
)
from yacht.workflows.benchmark_launch import BENCHMARK_LAUNCH_RESULT_PATH
from yacht.workflows.benchmark_launcher_handoff import BENCHMARK_LAUNCHER_HANDOFF_PATH
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.reports.next_steps import command_step, relocate_command_steps
from yacht.reports.preflight_evidence import PREFLIGHT_EVIDENCE_REPORT_PATH
from yacht.workflows.real_benchmark_eval import REAL_BENCHMARK_EVAL_PATH
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.reports.surface_summary import (
    format_surface_summary,
    load_logbook_surfaces,
    load_snapshot_surfaces,
)
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


def render_benchmark_status(logbook_dir: Path, output_format: str = "text") -> str:
    status = build_benchmark_status(logbook_dir)
    if output_format == "markdown":
        return _render_markdown(status)
    return _render_text(status)


def build_benchmark_status(logbook_dir: Path) -> dict[str, Any]:
    if is_logbook_candidate(logbook_dir):
        snapshot = require_logbook(logbook_dir)
        artifact_names = {artifact.name for artifact in snapshot.artifacts}
        if artifact_names & {"real_benchmark_repetitions", "benchmark_aggregate"}:
            return _build_repetition_benchmark_status(snapshot)
        if snapshot.state is LogbookState.LEGACY_SCORECARD_ONLY:
            return _build_legacy_benchmark_status(logbook_dir)
        return _build_indexed_benchmark_status(snapshot)
    return _build_legacy_benchmark_status(logbook_dir)


def _build_legacy_benchmark_status(logbook_dir: Path) -> dict[str, Any]:
    artifacts = [_artifact_status(logbook_dir, label, path) for label, path in _STAGES]
    return {
        "schema": "yacht.benchmark-status.v1",
        "logbook": str(logbook_dir),
        "status": _overall_status(artifacts),
        "surfaces": load_logbook_surfaces(logbook_dir),
        "artifacts": artifacts,
        "next_steps": _next_steps(logbook_dir, artifacts),
    }


def _build_indexed_benchmark_status(snapshot: LogbookSnapshot) -> dict[str, Any]:
    logbook_dir = snapshot.logbook
    artifacts = _indexed_artifacts(snapshot)
    return {
        "schema": "yacht.benchmark-status.v1",
        "logbook": str(logbook_dir),
        "status": snapshot.status,
        "run_kind": snapshot.run_kind,
        "regatta": snapshot.regatta,
        "course": snapshot.course,
        "comparisons": [
            {
                "name": comparison.name,
                "course": comparison.course,
                "vessels": list(comparison.vessels),
            }
            for comparison in snapshot.comparisons
        ],
        "surfaces": load_snapshot_surfaces(snapshot),
        "artifacts": artifacts,
        "next_steps": _next_steps(logbook_dir, artifacts),
    }


def _indexed_artifacts(snapshot: LogbookSnapshot) -> list[dict[str, Any]]:
    return [
        _artifact_status_from_path(
            _artifact_label(artifact.name),
            artifact.path,
        )
        for artifact in snapshot.artifacts
    ]


_STAGES = (
    ("real benchmark eval", REAL_BENCHMARK_EVAL_PATH),
    ("course handoff", COURSE_HANDOFF_PATH),
    ("preflight evidence", PREFLIGHT_EVIDENCE_REPORT_PATH),
    ("task attempt scorecard", TASK_ATTEMPT_SCORECARD_PATH),
    ("runtime instances", RUNTIME_INSTANCES_PLAN_PATH),
    ("benchmark execution plan", BENCHMARK_EXECUTION_PLAN_PATH),
    ("benchmark launcher handoff", BENCHMARK_LAUNCHER_HANDOFF_PATH),
    ("benchmark launch result", BENCHMARK_LAUNCH_RESULT_PATH),
    ("benchmark grading collection", BENCHMARK_GRADING_COLLECTION_PATH),
    ("benchmark scorecard", BENCHMARK_SCORECARD_PATH),
)


def _build_repetition_benchmark_status(
    snapshot: LogbookSnapshot,
) -> dict[str, Any]:
    logbook_dir = snapshot.logbook
    artifacts = _indexed_artifacts(snapshot)
    return {
        "schema": "yacht.benchmark-status.v1",
        "logbook": str(logbook_dir),
        "status": _repetition_overall_status(artifacts),
        "surfaces": load_snapshot_surfaces(snapshot),
        "artifacts": artifacts,
        "next_steps": _repetition_next_steps(logbook_dir, artifacts),
    }


def _artifact_status(
    logbook_dir: Path,
    label: str,
    relative_path: Path,
) -> dict[str, Any]:
    return _artifact_status_from_path(label, logbook_dir / relative_path)


def _artifact_status_from_path(
    label: str,
    path: Path,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "label": label,
        "path": str(path),
        "present": path.exists(),
        "state": "missing",
        "detail": "missing",
    }
    if not path.exists():
        return artifact
    if path.is_dir():
        artifact["state"] = "present"
        artifact["detail"] = "present"
        return artifact
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        artifact["state"] = "invalid"
        artifact["detail"] = f"invalid JSON: {error}"
        return artifact
    if not isinstance(payload, dict):
        artifact["state"] = "invalid"
        artifact["detail"] = "artifact must be a JSON object"
        return artifact
    state = str(payload.get("status") or payload.get("mode") or "present")
    artifact["state"] = state
    artifact["detail"] = _artifact_detail(payload, state)
    if "next_steps" in payload:
        artifact["next_steps"] = payload["next_steps"]
    return artifact


def _artifact_label(name: str) -> str:
    return name.replace("_", " ")


def _artifact_detail(payload: dict[str, Any], state: str) -> str:
    summary = payload.get("summary")
    if isinstance(summary, dict):
        parts = [
            f"{key}={value}"
            for key, value in summary.items()
            if isinstance(value, int | float | str | bool)
        ]
        if parts:
            return f"{state}; " + ", ".join(parts)
    return state


def _overall_status(artifacts: list[dict[str, Any]]) -> str:
    states = [str(artifact["state"]) for artifact in artifacts]
    if "invalid" in states:
        return "invalid"
    scorecard = _artifact_by_label(artifacts, "benchmark scorecard")
    if scorecard["present"]:
        return str(scorecard["state"])
    if any(artifact["present"] for artifact in artifacts):
        return "partial"
    return "empty"


def _repetition_overall_status(artifacts: list[dict[str, Any]]) -> str:
    states = [str(artifact["state"]) for artifact in artifacts]
    if "invalid" in states:
        return "invalid"
    repetitions = _artifact_by_label(artifacts, "real benchmark repetitions")
    if repetitions["present"]:
        return str(repetitions["state"])
    if any(artifact["present"] for artifact in artifacts):
        return "partial"
    return "empty"


def _next_steps(
    logbook_dir: Path,
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for label in (
        "benchmark scorecard",
        "real benchmark eval",
        "benchmark grading collection",
        "benchmark launch result",
    ):
        artifact = _artifact_by_label(artifacts, label)
        steps = artifact.get("next_steps")
        if isinstance(steps, list) and steps:
            return relocate_command_steps(steps, logbook_dir)

    if _artifact_by_label(artifacts, "benchmark scorecard")["present"]:
        return [
            command_step(
                label="Render benchmark report",
                reason="The scorecard exists; render the human-readable report.",
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "report",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        ]
    return [
        command_step(
            label="Run real benchmark eval",
            reason=(
                "No completed benchmark scorecard is available; start or rerun the "
                "real benchmark workflow."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "run",
                "<regatta.toml>",
                "--logbook",
                str(logbook_dir),
                "--workspace",
                ".",
            ],
        )
    ]


def _repetition_next_steps(
    logbook_dir: Path,
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    repetitions = _artifact_by_label(artifacts, "real benchmark repetitions")
    steps = repetitions.get("next_steps")
    if isinstance(steps, list) and steps:
        return relocate_command_steps(steps, logbook_dir)
    aggregate = _artifact_by_label(artifacts, "benchmark aggregate")
    if aggregate["present"]:
        return [
            command_step(
                label="Render benchmark report",
                reason=(
                    "The repeated-run aggregate exists; render the aggregate "
                    "resolution and usage report."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "report",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        ]
    return [
        command_step(
            label="Run repeated real benchmark eval",
            reason=(
                "No repeated benchmark aggregate is available; start or rerun "
                "the repeated benchmark workflow."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "run",
                "<regatta.toml>",
                "--logbook",
                str(logbook_dir),
                "--workspace",
                ".",
                "--repetitions",
                "3",
            ],
        )
    ]


def _artifact_by_label(
    artifacts: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    for artifact in artifacts:
        if artifact["label"] == label:
            return artifact
    return {
        "label": label,
        "path": "",
        "present": False,
        "state": "missing",
        "detail": "missing",
    }


def _render_text(status: dict[str, Any]) -> str:
    lines = [
        f"Benchmark status: {status['logbook']}",
        f"Status: {status['status']}",
        *_surface_text_lines(status),
        "",
        "state | artifact | path | detail",
    ]
    lines.extend(_artifact_row(artifact) for artifact in status["artifacts"])
    lines.extend(["", "Next steps:"])
    lines.extend(_text_next_step_lines(status["next_steps"]))
    return "\n".join(lines) + "\n"


def _render_markdown(status: dict[str, Any]) -> str:
    lines = [
        "## Benchmark status",
        "",
        f"- Logbook: {status['logbook']}",
        f"- Status: {status['status']}",
        *_surface_markdown_lines(status),
        "",
        "| State | Artifact | Path | Detail |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {artifact['state']} | {artifact['label']} | {artifact['path']} | "
        f"{artifact['detail']} |"
        for artifact in status["artifacts"]
    )
    lines.extend(["", "## Next steps", ""])
    lines.extend(_markdown_next_step_lines(status["next_steps"]))
    return "\n".join(lines) + "\n"


def _artifact_row(artifact: dict[str, Any]) -> str:
    return (
        f"{artifact['state']} | {artifact['label']} | "
        f"{artifact['path']} | {artifact['detail']}"
    )


def _surface_text_lines(status: dict[str, Any]) -> list[str]:
    summary = format_surface_summary(status.get("surfaces"))
    if summary is None:
        return []
    return [f"Surfaces: {summary}"]


def _surface_markdown_lines(status: dict[str, Any]) -> list[str]:
    summary = format_surface_summary(status.get("surfaces"))
    if summary is None:
        return []
    return [f"- Surfaces: {summary}"]


def _text_next_step_lines(steps: list[dict[str, Any]]) -> list[str]:
    if not steps:
        return ["- none"]
    lines = []
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step['label']}")
        lines.append(f"   command: {step['command_preview']}")
        lines.append(f"   reason: {step['reason']}")
    return lines


def _markdown_next_step_lines(steps: list[dict[str, Any]]) -> list[str]:
    if not steps:
        return ["- None"]
    lines = []
    for step in steps:
        lines.append(f"- {step['label']}: `{step['command_preview']}`")
        lines.append(f"  Reason: {step['reason']}")
    return lines
