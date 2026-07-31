from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.artifacts import (
    candidate_patches_path,
    grading_report_path,
    handoff_task_ids,
    validate_handoff_vessel,
    write_json_artifact,
)
from yacht.courses.handoff import build_course_handoff
from yacht.contracts.schemas import validate_course_grading_report_document
from yacht.domain.model import ConfigError


NATIVE_REPORT_COUNT_FIELDS = (
    "total_instances",
    "submitted_instances",
    "completed_instances",
    "resolved_instances",
    "unresolved_instances",
    "empty_patch_instances",
    "error_instances",
)
NATIVE_REPORT_ID_FIELDS = (
    "submitted_ids",
    "completed_ids",
    "incomplete_ids",
    "resolved_ids",
    "unresolved_ids",
    "empty_patch_ids",
    "error_ids",
)


def write_course_grading_report(
    *,
    config_path: Path,
    native_report_path: Path,
    logbook_dir: Path,
    vessel_name: str | None,
    grading_schema: str,
    native_schema_version: int,
    candidate_label: str,
    candidate_record_label: str,
) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    if vessel_name is not None:
        validate_handoff_vessel(handoff, vessel_name)
    candidate_path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    candidate_instance_ids = _load_candidate_instance_ids(
        candidate_path, candidate_label=candidate_label
    )
    native_report = load_native_report(native_report_path)
    validate_native_report(
        native_report,
        handoff_instance_ids=handoff_task_ids(handoff),
        candidate_instance_ids=candidate_instance_ids,
        native_schema_version=native_schema_version,
        candidate_record_label=candidate_record_label,
    )

    artifact = _grading_artifact(
        handoff=handoff,
        native_report=native_report,
        native_report_path=native_report_path,
        candidate_path=candidate_path,
        vessel_name=vessel_name,
        grading_schema=grading_schema,
    )
    validate_course_grading_report_document(artifact)
    grading_path = grading_report_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    write_json_artifact(grading_path, artifact)

    summary: dict[str, Any] = {
        "status": "validated",
        "adapter": str(handoff["adapter"]["kind"]),
        "dataset": str(handoff["adapter"]["dataset"]),
        "split": str(handoff["adapter"]["split"]),
        "submitted_instances": native_report["submitted_instances"],
        "resolved_instances": native_report["resolved_instances"],
        "resolution_rate": artifact["resolution_rate"],
        "grading_report_path": str(grading_path),
    }
    if vessel_name is not None:
        summary["vessel"] = vessel_name
    return summary


def _load_candidate_instance_ids(path: Path, *, candidate_label: str) -> set[str]:
    if not path.exists():
        raise ConfigError(f"{candidate_label} file not found: {path}")

    instance_ids = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ConfigError(
                f"{candidate_label} line {line_number} is not valid JSON: {error}"
            ) from error
        instance_id = record.get("instance_id") if isinstance(record, dict) else None
        if not isinstance(instance_id, str) or not instance_id:
            raise ConfigError(
                f"{candidate_label} line {line_number}.instance_id must be non-empty"
            )
        instance_ids.add(instance_id)
    if not instance_ids:
        raise ConfigError(f"{candidate_label} must contain at least one record")
    return instance_ids


def load_native_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"grading report file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"grading report file is not valid JSON: {error}") from error

    if not isinstance(payload, dict):
        raise ConfigError("grading report must be a JSON object")
    return payload


def validate_native_report(
    report: dict[str, Any],
    *,
    handoff_instance_ids: set[str],
    candidate_instance_ids: set[str],
    native_schema_version: int,
    candidate_record_label: str,
) -> None:
    for field in NATIVE_REPORT_COUNT_FIELDS:
        value = report.get(field)
        if not isinstance(value, int) or value < 0:
            raise ConfigError(f"grading report {field} must be an integer >= 0")
    for field in NATIVE_REPORT_ID_FIELDS:
        value = report.get(field)
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ConfigError(f"grading report {field} must be a list of strings")
    if report.get("schema_version") != native_schema_version:
        raise ConfigError(
            f"grading report schema_version must be {native_schema_version}"
        )

    submitted_ids = set(report["submitted_ids"])
    if not submitted_ids <= handoff_instance_ids:
        raise ConfigError(
            "grading report submitted_ids contains task outside course handoff"
        )
    if submitted_ids != candidate_instance_ids:
        raise ConfigError(
            "grading report submitted_ids must match "
            f"{candidate_record_label} instance_ids"
        )

    _require_count_matches(report, "submitted_instances", "submitted_ids")
    _require_count_matches(report, "completed_instances", "completed_ids")
    _require_count_matches(report, "resolved_instances", "resolved_ids")
    _require_count_matches(report, "unresolved_instances", "unresolved_ids")
    _require_count_matches(report, "empty_patch_instances", "empty_patch_ids")
    _require_count_matches(report, "error_instances", "error_ids")
    if report["total_instances"] != len(handoff_instance_ids):
        raise ConfigError("grading report total_instances must match course handoff")

    completed_ids = set(report["completed_ids"])
    for field in (
        "completed_ids",
        "incomplete_ids",
        "resolved_ids",
        "unresolved_ids",
        "empty_patch_ids",
        "error_ids",
    ):
        ids = set(report[field])
        if not ids <= submitted_ids:
            raise ConfigError(
                f"grading report {field} must be a subset of submitted_ids"
            )
    if not set(report["resolved_ids"]) <= completed_ids:
        raise ConfigError(
            "grading report resolved_ids must be a subset of completed_ids"
        )
    if not set(report["unresolved_ids"]) <= completed_ids:
        raise ConfigError(
            "grading report unresolved_ids must be a subset of completed_ids"
        )


def _require_count_matches(
    report: dict[str, Any],
    count_field: str,
    ids_field: str,
) -> None:
    if report[count_field] != len(set(report[ids_field])):
        raise ConfigError(f"grading report {count_field} must match {ids_field}")


def _grading_artifact(
    *,
    handoff: dict[str, Any],
    native_report: dict[str, Any],
    native_report_path: Path,
    candidate_path: Path,
    vessel_name: str | None,
    grading_schema: str,
) -> dict[str, Any]:
    submitted_instances = int(native_report["submitted_instances"])
    resolved_instances = int(native_report["resolved_instances"])
    artifact: dict[str, Any] = {
        "schema": grading_schema,
        "regatta": str(handoff["regatta"]),
        "course": str(handoff["course"]),
        "adapter": str(handoff["adapter"]["kind"]),
        "dataset": str(handoff["adapter"]["dataset"]),
        "split": str(handoff["adapter"]["split"]),
        "status": "validated",
        "source_report_path": str(native_report_path),
        "candidate_patches_path": str(candidate_path),
        "submitted_instances": submitted_instances,
        "resolved_instances": resolved_instances,
        "resolution_rate": (
            resolved_instances / submitted_instances if submitted_instances else 0.0
        ),
        "native_report": native_report,
    }
    if vessel_name is not None:
        artifact["vessel"] = vessel_name
    return artifact
