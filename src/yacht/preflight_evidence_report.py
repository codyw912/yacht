from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.course_handoff import COURSE_HANDOFF_PATH
from yacht.regatta import ConfigError
from yacht.schemas import (
    PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
    SchemaValidationError,
    validate_preflight_document,
    validate_preflight_evidence_report_document,
)


PREFLIGHT_EVIDENCE_REPORT_PATH = Path("preflight-evidence-report.json")


def write_preflight_evidence_report(logbook_dir: Path) -> dict[str, Any]:
    report = build_preflight_evidence_report(logbook_dir)
    _write_json(logbook_dir / PREFLIGHT_EVIDENCE_REPORT_PATH, report)
    return report


def build_preflight_evidence_report(logbook_dir: Path) -> dict[str, Any]:
    handoff = _load_handoff(logbook_dir)
    report = _build_report(logbook_dir, handoff)
    validate_preflight_evidence_report_document(report)
    return report


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


def _build_report(logbook_dir: Path, handoff: dict[str, Any]) -> dict[str, Any]:
    comparisons = [
        _comparison_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison=comparison,
        )
        for comparison in handoff["comparisons"]
    ]
    return {
        "schema": PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
        "regatta": str(handoff["regatta"]),
        "course": str(handoff["course"]),
        "status": _aggregate_status(
            [comparison["status"] for comparison in comparisons]
        ),
        "comparisons": comparisons,
    }


def _comparison_to_json(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    vessels = [
        _vessel_to_json(
            logbook_dir=logbook_dir,
            regatta_name=str(handoff["regatta"]),
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
    regatta_name: str,
    comparison_name: str,
    vessel_name: str,
) -> dict[str, Any]:
    artifact_path = logbook_dir / "preflight" / comparison_name / f"{vessel_name}.json"
    if not artifact_path.exists():
        return _vessel_report(
            vessel_name=vessel_name,
            artifact_path=artifact_path,
            artifact_present=False,
            status="missing-preflight",
            preflight_status="missing",
            reason="preflight-missing",
            error=None,
        )

    try:
        artifact = _load_preflight_artifact(artifact_path)
        _validate_artifact_identity(
            artifact=artifact,
            regatta_name=regatta_name,
            comparison_name=comparison_name,
            vessel_name=vessel_name,
        )
    except ConfigError as error:
        return _vessel_report(
            vessel_name=vessel_name,
            artifact_path=artifact_path,
            artifact_present=True,
            status="preflight-invalid",
            preflight_status="invalid",
            reason="preflight-invalid",
            error=str(error),
        )

    preflight_status = str(artifact["status"])
    if preflight_status == "passed":
        return _vessel_report(
            vessel_name=vessel_name,
            artifact_path=artifact_path,
            artifact_present=True,
            status="eligible",
            preflight_status=preflight_status,
            reason="preflight-passed",
            error=None,
        )
    status = f"preflight-{preflight_status}"
    return _vessel_report(
        vessel_name=vessel_name,
        artifact_path=artifact_path,
        artifact_present=True,
        status=status,
        preflight_status=preflight_status,
        reason=status,
        error=None,
    )


def _load_preflight_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"preflight artifact is not valid JSON: {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ConfigError(f"preflight artifact must be a JSON object: {path}")
    try:
        validate_preflight_document(payload)
    except SchemaValidationError as error:
        raise ConfigError(f"preflight artifact is invalid: {path}: {error}") from error
    return payload


def _validate_artifact_identity(
    *,
    artifact: dict[str, Any],
    regatta_name: str,
    comparison_name: str,
    vessel_name: str,
) -> None:
    expected = {
        "regatta": regatta_name,
        "comparison": comparison_name,
        "vessel": vessel_name,
    }
    mismatches = [
        f"{key}={artifact.get(key)!r}, expected {value!r}"
        for key, value in expected.items()
        if artifact.get(key) != value
    ]
    if mismatches:
        raise ConfigError(
            "preflight artifact identity does not match course handoff: "
            f"{', '.join(mismatches)}"
        )


def _vessel_report(
    *,
    vessel_name: str,
    artifact_path: Path,
    artifact_present: bool,
    status: str,
    preflight_status: str,
    reason: str,
    error: str | None,
) -> dict[str, Any]:
    report = {
        "name": vessel_name,
        "status": status,
        "eligible_for_benchmark": status == "eligible",
        "reason": reason,
        "preflight_artifact_path": str(artifact_path),
        "preflight_artifact_present": artifact_present,
        "preflight_status": preflight_status,
    }
    if error is not None:
        report["error"] = error
    return report


def _aggregate_status(statuses: list[str]) -> str:
    if all(status in {"ready", "eligible"} for status in statuses):
        return "ready"
    return "blocked"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
