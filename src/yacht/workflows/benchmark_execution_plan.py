from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.preflight.gate import PreflightGate, preflight_gate
from yacht.domain.model import ConfigError
from yacht.runtimes.snapshot_gate import RuntimeSnapshotGate, runtime_snapshot_gate
from yacht.contracts.schemas import (
    BENCHMARK_EXECUTION_PLAN_SCHEMA,
    validate_benchmark_execution_plan_document,
)
from yacht.courses.artifacts import (
    candidate_patches_path,
    grading_report_path,
)


BENCHMARK_EXECUTION_PLAN_PATH = Path("benchmark-execution-plan.json")


def write_benchmark_execution_plan(logbook_dir: Path) -> dict[str, Any]:
    handoff = _load_handoff(logbook_dir)
    plan = _build_plan(logbook_dir, handoff)
    validate_benchmark_execution_plan_document(plan)
    _write_json(logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH, plan)
    return plan


def _load_handoff(logbook_dir: Path) -> dict[str, Any]:
    handoff_path = logbook_dir / COURSE_HANDOFF_PATH
    if not handoff_path.exists():
        raise ConfigError(f"course handoff artifact not found: {handoff_path}")
    return _load_json_object(handoff_path, "course handoff artifact")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _build_plan(logbook_dir: Path, handoff: dict[str, Any]) -> dict[str, Any]:
    comparisons = [
        _comparison_to_json(logbook_dir, handoff, comparison)
        for comparison in handoff["comparisons"]
    ]
    return {
        "schema": BENCHMARK_EXECUTION_PLAN_SCHEMA,
        "regatta": str(handoff["regatta"]),
        "course": str(handoff["course"]),
        "adapter": {
            "kind": str(handoff["adapter"]["kind"]),
            "dataset": str(handoff["adapter"]["dataset"]),
            "split": str(handoff["adapter"]["split"]),
            "harness": str(handoff["adapter"]["harness"]),
        },
        "status": _aggregate_status(
            [comparison["status"] for comparison in comparisons]
        ),
        "comparisons": comparisons,
    }


def _comparison_to_json(
    logbook_dir: Path,
    handoff: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    vessels = [
        _vessel_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison_name=str(comparison["name"]),
            vessel_name=str(vessel_name),
        )
        for vessel_name in comparison["vessels"]
    ]
    return {
        "name": str(comparison["name"]),
        "course": str(comparison["course"]),
        "status": _aggregate_status([vessel["status"] for vessel in vessels]),
        "vessels": vessels,
    }


def _vessel_to_json(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    comparison_name: str,
    vessel_name: str,
) -> dict[str, Any]:
    candidate_path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    grading_path = grading_report_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    candidate_present = candidate_path.exists()
    grading_present = grading_path.exists()
    gate = preflight_gate(
        logbook_dir=logbook_dir,
        regatta_name=str(handoff["regatta"]),
        comparison_name=comparison_name,
        vessel_name=vessel_name,
    )
    snapshot_gate = runtime_snapshot_gate(
        logbook_dir=logbook_dir,
        regatta_name=str(handoff["regatta"]),
        course_name=str(handoff["course"]),
        comparison_name=comparison_name,
        vessel_name=vessel_name,
    )
    return {
        "name": vessel_name,
        "status": _vessel_status(
            candidate_present=candidate_present,
            grading_present=grading_present,
            gate=gate,
            snapshot_gate=snapshot_gate,
        ),
        "candidate_patches_path": str(candidate_path),
        "candidate_patches_present": candidate_present,
        "grading_report_path": str(grading_path),
        "grading_report_present": grading_present,
        "preflight_artifact_path": str(gate.artifact_path),
        "preflight_artifact_present": gate.artifact_present,
        "preflight_status": gate.status,
        "runtime_instances_artifact_path": str(snapshot_gate.artifact_path),
        "runtime_instances_artifact_present": snapshot_gate.artifact_present,
        "runtime_snapshot_status": snapshot_gate.status,
    }


def _vessel_status(
    *,
    candidate_present: bool,
    grading_present: bool,
    gate: PreflightGate,
    snapshot_gate: RuntimeSnapshotGate,
) -> str:
    if grading_present:
        return "graded"
    if not candidate_present:
        return "missing-candidate-patches"
    if not gate.artifact_present:
        return "missing-preflight"
    if not gate.passed:
        return "preflight-failed"
    if not snapshot_gate.matched:
        return "missing-runtime-snapshot"
    return "ready-for-grading"


def _aggregate_status(statuses: list[str]) -> str:
    if all(status in {"graded", "complete"} for status in statuses):
        return "complete"
    if all(status == "ready-for-grading" for status in statuses):
        return "ready-for-grading"
    if all(
        status
        in {
            "missing-candidate-patches",
            "missing-preflight",
            "missing-runtime-snapshot",
            "missing-inputs",
        }
        for status in statuses
    ):
        return "missing-inputs"
    if all(status in {"preflight-failed", "blocked"} for status in statuses):
        return "blocked"
    return "mixed"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
