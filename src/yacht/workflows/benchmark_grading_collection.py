from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.registry import course_adapter_block
from yacht.courses.registry import evaluator_adapter
from yacht.workflows.benchmark_launch import BENCHMARK_LAUNCH_RESULT_PATH
from yacht.workflows.benchmark_launcher_handoff import (
    native_report_path_from_launcher_handoff,
)
from yacht.reports.next_steps import command_step
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_benchmark_launch_result_document,
)


BENCHMARK_GRADING_COLLECTION_PATH = Path("benchmark-grading-collection.json")
BENCHMARK_GRADING_COLLECTION_SCHEMA = "yacht.benchmark-grading-collection.v1"


def collect_benchmark_grading_reports(
    *,
    config_path: Path,
    logbook_dir: Path,
) -> dict[str, Any]:
    launch_result = _load_launch_result(logbook_dir)
    comparisons = [
        _comparison_to_json(
            config_path=config_path,
            logbook_dir=logbook_dir,
            comparison=comparison,
            adapter_kind=str(launch_result["adapter"]["kind"]),
        )
        for comparison in launch_result["comparisons"]
    ]
    summary = _summary(comparisons)
    collection = {
        "schema": BENCHMARK_GRADING_COLLECTION_SCHEMA,
        "regatta": str(launch_result["regatta"]),
        "course": str(launch_result["course"]),
        "adapter": course_adapter_block(launch_result["adapter"]),
        "status": _status(summary),
        "summary": summary,
        "next_steps": _next_steps(logbook_dir, summary),
        "comparisons": comparisons,
    }
    _write_json(logbook_dir / BENCHMARK_GRADING_COLLECTION_PATH, collection)
    return collection


def _load_launch_result(logbook_dir: Path) -> dict[str, Any]:
    path = logbook_dir / BENCHMARK_LAUNCH_RESULT_PATH
    if not path.exists():
        raise ConfigError(f"benchmark launch result artifact not found: {path}")
    launch_result = _load_json_object(path, "benchmark launch result artifact")
    try:
        validate_benchmark_launch_result_document(launch_result)
    except SchemaValidationError as error:
        raise ConfigError(str(error)) from error
    return launch_result


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _comparison_to_json(
    *,
    config_path: Path,
    logbook_dir: Path,
    comparison: dict[str, Any],
    adapter_kind: str,
) -> dict[str, Any]:
    vessels = [
        _vessel_to_json(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel=vessel,
            adapter_kind=adapter_kind,
        )
        for vessel in comparison["vessels"]
    ]
    return {
        "name": str(comparison["name"]),
        "course": str(comparison["course"]),
        "status": _status(_summary_from_vessels(vessels)),
        "vessels": vessels,
    }


def _vessel_to_json(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel: dict[str, Any],
    adapter_kind: str,
) -> dict[str, Any]:
    vessel_name = str(vessel["name"])
    adapter = evaluator_adapter(adapter_kind)
    if vessel["status"] != "completed":
        return {
            "name": vessel_name,
            "launch_status": str(vessel["status"]),
            "status": "skipped",
            "reason": f"launch-{vessel['status']}",
        }
    try:
        native_report_path = native_report_path_from_launcher_handoff(
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )
    except ConfigError as error:
        return {
            "name": vessel_name,
            "launch_status": str(vessel["status"]),
            "status": "missing-native-report",
            "native_report_dir": str(vessel["native_report_dir"]),
            "error": str(error),
        }

    try:
        grading_summary = adapter.write_grading_report(
            config_path=config_path,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )
    except ConfigError as error:
        return {
            "name": vessel_name,
            "launch_status": str(vessel["status"]),
            "status": "invalid-native-report",
            "native_report_path": str(native_report_path),
            "error": str(error),
        }

    return {
        "name": vessel_name,
        "launch_status": str(vessel["status"]),
        "status": "collected",
        "native_report_path": str(native_report_path),
        "grading_report_path": str(grading_summary["grading_report_path"]),
        "submitted_instances": int(grading_summary["submitted_instances"]),
        "resolved_instances": int(grading_summary["resolved_instances"]),
        "resolution_rate": float(grading_summary["resolution_rate"]),
    }


def _summary(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    vessels = [vessel for comparison in comparisons for vessel in comparison["vessels"]]
    return _summary_from_vessels(vessels)


def _summary_from_vessels(vessels: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_vessels": len(vessels),
        "completed_launches": sum(
            1 for vessel in vessels if vessel["launch_status"] == "completed"
        ),
        "collected_reports": sum(
            1 for vessel in vessels if vessel["status"] == "collected"
        ),
        "missing_native_reports": sum(
            1 for vessel in vessels if vessel["status"] == "missing-native-report"
        ),
        "invalid_native_reports": sum(
            1 for vessel in vessels if vessel["status"] == "invalid-native-report"
        ),
        "skipped_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "skipped"
        ),
    }


def _status(summary: dict[str, int]) -> str:
    if summary["completed_launches"] == 0:
        return "blocked"
    if (
        summary["collected_reports"] == summary["total_vessels"]
        and summary["missing_native_reports"] == 0
        and summary["invalid_native_reports"] == 0
        and summary["skipped_vessels"] == 0
    ):
        return "complete"
    return "partial"


def _next_steps(logbook_dir: Path, summary: dict[str, int]) -> list[dict[str, object]]:
    steps = []
    if summary["collected_reports"]:
        steps.append(
            command_step(
                label="Write benchmark scorecard",
                reason=(
                    "At least one validated grading report is available; summarize "
                    "benchmark results into a scorecard."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "internals",
                    "benchmark-scorecard",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        )
    if summary["missing_native_reports"] or summary["invalid_native_reports"]:
        steps.append(
            command_step(
                label="Rerun benchmark launch",
                reason=(
                    "Some native benchmark reports are missing or invalid; inspect "
                    "the per-vessel errors in this artifact, then rerun launch or "
                    "collection."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "internals",
                    "benchmark-launch",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        )
    if not steps:
        steps.append(
            command_step(
                label="Review launch result",
                reason=(
                    "No grading reports were collected; inspect launch status before "
                    "building a scorecard."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "internals",
                    "benchmark-launch",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        )
    return steps


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
