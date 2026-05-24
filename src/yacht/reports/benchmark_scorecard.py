from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.registry import benchmark_adapter
from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.next_steps import command_step
from yacht.reports.preflight_evidence import build_preflight_evidence_report
from yacht.domain.model import ConfigError
from yacht.schemas import (
    BENCHMARK_SCORECARD_SCHEMA,
    validate_benchmark_scorecard_document,
)
from yacht.courses.swe_bench.artifacts import grading_report_path, vessels_artifact_dir


BENCHMARK_SCORECARD_PATH = Path("benchmark-scorecard.json")


def write_benchmark_scorecard(logbook_dir: Path) -> dict[str, Any]:
    handoff = _load_handoff(logbook_dir)
    gradings = _load_gradings(logbook_dir, handoff)
    preflight_report = build_preflight_evidence_report(logbook_dir)
    scorecard = _build_scorecard(handoff, gradings, preflight_report)
    scorecard["next_steps"] = _next_steps(logbook_dir, scorecard["comparisons"])
    validate_benchmark_scorecard_document(scorecard)
    _write_json(logbook_dir / BENCHMARK_SCORECARD_PATH, scorecard)
    return scorecard


def _load_handoff(logbook_dir: Path) -> dict[str, Any]:
    handoff_path = logbook_dir / COURSE_HANDOFF_PATH
    if not handoff_path.exists():
        raise ConfigError(f"course handoff artifact not found: {handoff_path}")
    return _load_json_object(handoff_path, "course handoff artifact")


def _load_gradings(logbook_dir: Path, handoff: dict[str, Any]) -> list[dict[str, Any]]:
    grading_paths = _grading_paths(logbook_dir, handoff)
    if not grading_paths:
        expected_path = logbook_dir / str(handoff["expected_outputs"]["grading_report"])
        raise ConfigError(f"validated grading report not found: {expected_path}")
    adapter = benchmark_adapter(str(handoff["adapter"]["kind"]))
    return [_load_grading(path, expected_schema=adapter.grading_schema) for path in grading_paths]


def _grading_paths(logbook_dir: Path, handoff: dict[str, Any]) -> list[Path]:
    paths = []
    default_path = grading_report_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=None,
    )
    if default_path.exists():
        paths.append(default_path)
    vessels_dir = vessels_artifact_dir(
        logbook_dir=logbook_dir,
        handoff=handoff,
    )
    paths.extend(sorted(vessels_dir.glob("*/grading-report.json")))
    return paths


def _load_grading(grading_path: Path, *, expected_schema: str) -> dict[str, Any]:
    grading = _load_json_object(grading_path, "validated grading report")
    if grading.get("schema") != expected_schema:
        raise ConfigError("validated grading report has unsupported schema")
    return grading


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _build_scorecard(
    handoff: dict[str, Any],
    gradings: list[dict[str, Any]],
    preflight_report: dict[str, Any],
) -> dict[str, Any]:
    measured_by_vessel = _measured_by_vessel(gradings)
    preflight_by_vessel = _preflight_by_comparison_and_vessel(preflight_report)
    comparisons = [
        _comparison_to_json(comparison, measured_by_vessel, preflight_by_vessel)
        for comparison in handoff["comparisons"]
    ]
    scorecard = {
        "schema": BENCHMARK_SCORECARD_SCHEMA,
        "regatta": str(handoff["regatta"]),
        "course": str(handoff["course"]),
        "adapter": {
            "kind": str(handoff["adapter"]["kind"]),
            "dataset": str(handoff["adapter"]["dataset"]),
            "split": str(handoff["adapter"]["split"]),
        },
        "status": _scorecard_status(comparisons),
        "summary": _scorecard_summary(comparisons),
        "comparisons": comparisons,
    }
    return scorecard


def _measured_by_vessel(
    gradings: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    measured = {}
    for grading in gradings:
        vessel_name = _vessel_name_from_grading(grading)
        if vessel_name in measured:
            raise ConfigError(
                f"multiple validated grading reports found for vessel {vessel_name}"
            )
        native_report = grading["native_report"]
        submitted_ids = set(native_report["submitted_ids"])
        measured[vessel_name] = {
            "status": "measured",
            "submitted_instances": int(grading["submitted_instances"]),
            "resolved_instances": int(grading["resolved_instances"]),
            "resolution_rate": float(grading["resolution_rate"]),
            "resolved_ids": [
                instance_id
                for instance_id in native_report["resolved_ids"]
                if instance_id in submitted_ids
            ],
            "unresolved_ids": [
                instance_id
                for instance_id in native_report["unresolved_ids"]
                if instance_id in submitted_ids
            ],
        }
        task_diagnostics = _task_diagnostics(native_report, submitted_ids)
        if task_diagnostics:
            measured[vessel_name]["task_diagnostics"] = task_diagnostics
    return measured


def _preflight_by_comparison_and_vessel(
    preflight_report: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(comparison["name"]), str(vessel["name"])): vessel
        for comparison in preflight_report["comparisons"]
        for vessel in comparison["vessels"]
    }


def _vessel_name_from_grading(grading: dict[str, Any]) -> str:
    vessel_name = grading.get("vessel")
    if isinstance(vessel_name, str) and vessel_name:
        return vessel_name
    native_report = grading["native_report"]
    submitted_ids = native_report["submitted_ids"]
    if not submitted_ids:
        return ""
    candidate_path = Path(str(grading["candidate_patches_path"]))
    for line in candidate_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["instance_id"] == submitted_ids[0]:
            return str(record["model_name_or_path"])
    raise ConfigError("candidate patches do not contain submitted grading ids")


def _task_diagnostics(
    native_report: dict[str, Any],
    submitted_ids: set[str],
) -> list[dict[str, Any]]:
    instance_results = native_report.get("instance_results")
    if not isinstance(instance_results, list):
        return []
    diagnostics = []
    for result in instance_results:
        if not isinstance(result, dict):
            continue
        instance_id = result.get("instance_id")
        if not isinstance(instance_id, str) or instance_id not in submitted_ids:
            continue
        diagnostics.append(
            {
                "task": instance_id,
                "result": (
                    "resolved" if result.get("resolved") is True else "unresolved"
                ),
                "reason": str(result.get("reason", "unresolved")),
                "response_matched": result.get("response_matched") is True,
                "missing_response_fields": _string_list(
                    result.get("missing_response_fields")
                ),
                "mismatched_response_fields": _string_list(
                    result.get("mismatched_response_fields")
                ),
                "expected_tool_calls": _string_list(result.get("expected_tool_calls")),
                "observed_tool_calls": _string_list(
                    result.get("observed_tool_calls")
                ),
                "missing_tool_calls": _string_list(result.get("missing_tool_calls")),
            }
        )
    return diagnostics


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _comparison_to_json(
    comparison: dict[str, Any],
    measured_by_vessel: dict[str, dict[str, Any]],
    preflight_by_vessel: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    comparison_name = str(comparison["name"])
    vessels = [
        _vessel_score(
            comparison_name,
            vessel_name,
            measured_by_vessel,
            preflight_by_vessel,
        )
        for vessel_name in comparison["vessels"]
    ]
    return {
        "name": comparison_name,
        "course": str(comparison["course"]),
        "summary": _comparison_summary(vessels),
        "delta": _comparison_delta(vessels),
        "vessels": vessels,
    }


def _vessel_score(
    comparison_name: str,
    vessel_name: str,
    measured_by_vessel: dict[str, dict[str, Any]],
    preflight_by_vessel: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    preflight = preflight_by_vessel[(comparison_name, vessel_name)]
    preflight_summary = {
        "eligible_for_benchmark": bool(preflight["eligible_for_benchmark"]),
        "preflight_status": str(preflight["preflight_status"]),
        "preflight_reason": str(preflight["reason"]),
        "preflight_artifact_path": str(preflight["preflight_artifact_path"]),
    }
    if "error" in preflight:
        preflight_summary["preflight_error"] = str(preflight["error"])
    measured = measured_by_vessel.get(vessel_name)
    if measured is None:
        return {
            "name": vessel_name,
            "status": "missing",
            "submitted_instances": 0,
            "resolved_instances": 0,
            "resolution_rate": 0.0,
            **preflight_summary,
        }
    return {
        "name": vessel_name,
        **measured,
        **preflight_summary,
    }


def _comparison_summary(vessels: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_vessels": len(vessels),
        "eligible_vessels": sum(
            1 for vessel in vessels if vessel["eligible_for_benchmark"]
        ),
        "blocked_vessels": sum(
            1 for vessel in vessels if not vessel["eligible_for_benchmark"]
        ),
        "measured_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "measured"
        ),
        "missing_result_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "missing"
        ),
    }


def _comparison_delta(vessels: list[dict[str, Any]]) -> dict[str, int | float | str]:
    baseline = vessels[0]
    challenger = vessels[1]
    return {
        "baseline_vessel": str(baseline["name"]),
        "challenger_vessel": str(challenger["name"]),
        "resolved_instances_delta": int(challenger["resolved_instances"])
        - int(baseline["resolved_instances"]),
        "resolution_rate_delta": float(challenger["resolution_rate"])
        - float(baseline["resolution_rate"]),
    }


def _scorecard_summary(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    summary_keys = (
        "total_vessels",
        "eligible_vessels",
        "blocked_vessels",
        "measured_vessels",
        "missing_result_vessels",
    )
    return {
        "total_comparisons": len(comparisons),
        **{
            key: sum(comparison["summary"][key] for comparison in comparisons)
            for key in summary_keys
        },
    }


def _scorecard_status(comparisons: list[dict[str, Any]]) -> str:
    statuses = [
        vessel["status"]
        for comparison in comparisons
        for vessel in comparison["vessels"]
    ]
    if all(status == "measured" for status in statuses):
        return "complete"
    if any(status == "measured" for status in statuses):
        return "partial"
    return "empty"


def _next_steps(
    logbook_dir: Path,
    comparisons: list[dict[str, Any]],
) -> list[dict[str, object]]:
    steps = [
        command_step(
            label="Render benchmark report",
            reason=(
                "The benchmark scorecard is ready; render a human-readable report "
                "with benchmark outcomes, usage, and artifact paths."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "benchmark-report",
                "--logbook",
                str(logbook_dir),
            ],
        ),
    ]
    inspection_step = _inspection_step(logbook_dir, comparisons)
    if inspection_step is not None:
        steps.append(inspection_step)
    steps.append(
        command_step(
            label="Write markdown benchmark report",
            reason=(
                "Use the markdown report when sharing benchmark results outside the "
                "terminal."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "benchmark-report",
                "--logbook",
                str(logbook_dir),
                "--format",
                "markdown",
                "--output",
                str(logbook_dir / "benchmark-report.md"),
            ],
        ),
    )
    return steps


def _inspection_step(
    logbook_dir: Path,
    comparisons: list[dict[str, Any]],
) -> dict[str, object] | None:
    target = _inspection_target(comparisons)
    if target is None:
        return None
    vessel_name, task_id = target
    return command_step(
        label="Inspect filtered benchmark details",
        reason=(
            "Use a filtered report when investigating a specific vessel/task "
            "outcome, usage, and artifact path set."
        ),
        command=[
            "uv",
            "run",
            "yacht",
            "benchmark-report",
            "--logbook",
            str(logbook_dir),
            "--vessel",
            vessel_name,
            "--task",
            task_id,
        ],
    )


def _inspection_target(
    comparisons: list[dict[str, Any]],
) -> tuple[str, str] | None:
    for comparison in comparisons:
        challenger_name = str(comparison["delta"]["challenger_vessel"])
        for vessel in _inspection_ordered_vessels(
            comparison["vessels"],
            challenger_name,
        ):
            task_ids = [
                *[str(task_id) for task_id in vessel.get("resolved_ids", [])],
                *[str(task_id) for task_id in vessel.get("unresolved_ids", [])],
            ]
            if task_ids:
                return str(vessel["name"]), task_ids[0]
    return None


def _inspection_ordered_vessels(
    vessels: list[dict[str, Any]],
    challenger_name: str,
) -> list[dict[str, Any]]:
    return [
        *[vessel for vessel in vessels if str(vessel["name"]) == challenger_name],
        *[vessel for vessel in vessels if str(vessel["name"]) != challenger_name],
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
