from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.course_handoff import COURSE_HANDOFF_PATH
from yacht.preflight_evidence_report import build_preflight_evidence_report
from yacht.regatta import ConfigError
from yacht.schemas import (
    BENCHMARK_SCORECARD_SCHEMA,
    validate_benchmark_scorecard_document,
)
from yacht.swebench_artifacts import grading_report_path, vessels_artifact_dir


BENCHMARK_SCORECARD_PATH = Path("benchmark-scorecard.json")


def write_benchmark_scorecard(logbook_dir: Path) -> dict[str, Any]:
    handoff = _load_handoff(logbook_dir)
    gradings = _load_gradings(logbook_dir, handoff)
    preflight_report = build_preflight_evidence_report(logbook_dir)
    scorecard = _build_scorecard(handoff, gradings, preflight_report)
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
    return [_load_grading(path) for path in grading_paths]


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


def _load_grading(grading_path: Path) -> dict[str, Any]:
    grading = _load_json_object(grading_path, "validated grading report")
    if grading.get("schema") != "yacht.swe-bench-grading.v1":
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
