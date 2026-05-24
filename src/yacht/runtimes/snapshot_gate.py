from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.schemas import SchemaValidationError, validate_runtime_instances_document


@dataclass(frozen=True)
class RuntimeSnapshotGate:
    artifact_path: Path
    artifact_present: bool
    status: str
    matched: bool


def runtime_snapshot_gate(
    *,
    logbook_dir: Path,
    regatta_name: str,
    course_name: str,
    comparison_name: str,
    vessel_name: str,
) -> RuntimeSnapshotGate:
    artifact_path = logbook_dir / RUNTIME_INSTANCES_PLAN_PATH
    if not artifact_path.exists():
        return RuntimeSnapshotGate(
            artifact_path=artifact_path,
            artifact_present=False,
            status="missing",
            matched=False,
        )

    artifact = _load_runtime_instances_artifact(artifact_path)
    _validate_artifact_identity(
        artifact=artifact,
        artifact_path=artifact_path,
        regatta_name=regatta_name,
        course_name=course_name,
        comparison_name=comparison_name,
        vessel_name=vessel_name,
    )
    return RuntimeSnapshotGate(
        artifact_path=artifact_path,
        artifact_present=True,
        status="matched",
        matched=True,
    )


def _load_runtime_instances_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"runtime instances artifact is not valid JSON: {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ConfigError(f"runtime instances artifact must be a JSON object: {path}")
    try:
        validate_runtime_instances_document(payload)
    except SchemaValidationError as error:
        raise ConfigError(
            f"runtime instances artifact is invalid: {path}: {error}"
        ) from error
    return payload


def _validate_artifact_identity(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    regatta_name: str,
    course_name: str,
    comparison_name: str,
    vessel_name: str,
) -> None:
    expected = {
        "regatta": regatta_name,
        "course": course_name,
    }
    mismatches = [
        f"{key}={artifact.get(key)!r}, expected {value!r}"
        for key, value in expected.items()
        if artifact.get(key) != value
    ]
    if mismatches:
        raise ConfigError(
            "runtime instances artifact identity does not match benchmark handoff: "
            f"{artifact_path}: {', '.join(mismatches)}"
        )
    _find_vessel_snapshot(
        artifact=artifact,
        artifact_path=artifact_path,
        comparison_name=comparison_name,
        vessel_name=vessel_name,
    )


def _find_vessel_snapshot(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    comparison_name: str,
    vessel_name: str,
) -> dict[str, Any]:
    comparisons = [
        comparison
        for comparison in artifact["comparisons"]
        if comparison["name"] == comparison_name
    ]
    if not comparisons:
        raise ConfigError(
            "runtime instances artifact does not contain comparison "
            f"{comparison_name}: {artifact_path}"
        )
    vessels = [
        vessel
        for comparison in comparisons
        for vessel in comparison["vessels"]
        if vessel["name"] == vessel_name
    ]
    if not vessels:
        raise ConfigError(
            "runtime instances artifact does not contain vessel "
            f"{vessel_name}: {artifact_path}"
        )
    if len(vessels) > 1:
        raise ConfigError(
            "runtime instances artifact contains multiple entries for vessel "
            f"{vessel_name}: {artifact_path}"
        )
    return vessels[0]
