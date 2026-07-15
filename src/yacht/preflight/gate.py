from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError
from yacht.contracts.schemas import SchemaValidationError, validate_preflight_document


@dataclass(frozen=True)
class PreflightGate:
    artifact_path: Path
    artifact_present: bool
    status: str
    passed: bool


def preflight_gate(
    *,
    logbook_dir: Path,
    regatta_name: str,
    comparison_name: str,
    vessel_name: str,
) -> PreflightGate:
    artifact_path = logbook_dir / "preflight" / comparison_name / f"{vessel_name}.json"
    if not artifact_path.exists():
        return PreflightGate(
            artifact_path=artifact_path,
            artifact_present=False,
            status="missing",
            passed=False,
        )

    artifact = _load_preflight_artifact(artifact_path)
    _validate_artifact_identity(
        artifact=artifact,
        artifact_path=artifact_path,
        regatta_name=regatta_name,
        comparison_name=comparison_name,
        vessel_name=vessel_name,
    )
    status = str(artifact["status"])
    return PreflightGate(
        artifact_path=artifact_path,
        artifact_present=True,
        status=status,
        passed=status == "passed",
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
    artifact_path: Path,
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
            "preflight artifact identity does not match benchmark handoff: "
            f"{artifact_path}: {', '.join(mismatches)}"
        )
