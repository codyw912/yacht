from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.reports.benchmark_aggregate import BENCHMARK_AGGREGATE_PATH
from yacht.workflows.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.workflows.benchmark_grading_collection import BENCHMARK_GRADING_COLLECTION_PATH
from yacht.workflows.benchmark_launch import BENCHMARK_LAUNCH_RESULT_PATH
from yacht.workflows.benchmark_launcher_handoff import BENCHMARK_LAUNCHER_HANDOFF_PATH
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.reports.next_steps import command_step
from yacht.reports.preflight_evidence import PREFLIGHT_EVIDENCE_REPORT_PATH
from yacht.workflows.real_benchmark_eval import REAL_BENCHMARK_EVAL_PATH
from yacht.workflows.real_benchmark_repetitions import REAL_BENCHMARK_REPETITIONS_PATH
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.reports.surface_summary import format_surface_summary
from yacht.reports.surface_summary import load_logbook_surfaces
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


def render_benchmark_status(logbook_dir: Path, output_format: str = "text") -> str:
    status = build_benchmark_status(logbook_dir)
    if output_format == "markdown":
        return _render_markdown(status)
    return _render_text(status)


def build_benchmark_status(logbook_dir: Path) -> dict[str, Any]:
    if _is_repetition_logbook(logbook_dir):
        return _build_repetition_benchmark_status(logbook_dir)
    artifacts = [_artifact_status(logbook_dir, label, path) for label, path in _STAGES]
    return {
        "schema": "yacht.benchmark-status.v1",
        "logbook": str(logbook_dir),
        "status": _overall_status(artifacts),
        "surfaces": load_logbook_surfaces(logbook_dir),
        "artifacts": artifacts,
        "next_steps": _next_steps(logbook_dir, artifacts),
    }


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


_REPETITION_STAGES = (
    ("real benchmark repetitions", REAL_BENCHMARK_REPETITIONS_PATH),
    ("benchmark aggregate", BENCHMARK_AGGREGATE_PATH),
)


def _is_repetition_logbook(logbook_dir: Path) -> bool:
    return any((logbook_dir / path).exists() for _, path in _REPETITION_STAGES)


def _build_repetition_benchmark_status(logbook_dir: Path) -> dict[str, Any]:
    artifacts = [
        _artifact_status(logbook_dir, label, path) for label, path in _REPETITION_STAGES
    ]
    return {
        "schema": "yacht.benchmark-status.v1",
        "logbook": str(logbook_dir),
        "status": _repetition_overall_status(artifacts),
        "surfaces": load_logbook_surfaces(logbook_dir),
        "artifacts": artifacts,
        "next_steps": _repetition_next_steps(logbook_dir, artifacts),
    }


def _artifact_status(
    logbook_dir: Path,
    label: str,
    relative_path: Path,
) -> dict[str, Any]:
    path = logbook_dir / relative_path
    artifact: dict[str, Any] = {
        "label": label,
        "path": str(path),
        "present": path.exists(),
        "state": "missing",
        "detail": "missing",
    }
    if not path.exists():
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
            return [step for step in steps if isinstance(step, dict)]

    if _artifact_by_label(artifacts, "benchmark scorecard")["present"]:
        return [
            command_step(
                label="Render benchmark report",
                reason="The scorecard exists; render the human-readable report.",
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "benchmark-report",
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
                "real-benchmark-eval",
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
        return [step for step in steps if isinstance(step, dict)]
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
                    "benchmark-report",
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
                "real-benchmark-repetitions",
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
    raise KeyError(label)


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
