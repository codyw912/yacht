from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError


def candidate_patches_path(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    vessel_name: str | None,
) -> Path:
    if vessel_name is None:
        return logbook_dir / str(handoff["expected_outputs"]["candidate_patches"])
    return (
        vessel_artifact_dir(
            logbook_dir=logbook_dir,
            handoff=handoff,
            vessel_name=vessel_name,
        )
        / "candidate-patches.jsonl"
    )


def grading_report_path(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    vessel_name: str | None,
) -> Path:
    if vessel_name is None:
        return logbook_dir / str(handoff["expected_outputs"]["grading_report"])
    return (
        vessel_artifact_dir(
            logbook_dir=logbook_dir,
            handoff=handoff,
            vessel_name=vessel_name,
        )
        / "grading-report.json"
    )


def vessel_artifact_dir(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    vessel_name: str,
) -> Path:
    return vessels_artifact_dir(
        logbook_dir=logbook_dir, handoff=handoff
    ) / safe_vessel_path_name(vessel_name)


def vessels_artifact_dir(*, logbook_dir: Path, handoff: dict[str, Any]) -> Path:
    return adapter_artifact_dir(logbook_dir=logbook_dir, handoff=handoff) / "vessels"


def adapter_artifact_dir(*, logbook_dir: Path, handoff: dict[str, Any]) -> Path:
    return logbook_dir / "course-handoff" / str(handoff["adapter"]["kind"])


def validate_handoff_vessel(handoff: dict[str, Any], vessel_name: str) -> None:
    safe_vessel_path_name(vessel_name)
    if vessel_name not in comparison_vessel_names(handoff):
        raise ConfigError(f"vessel {vessel_name} is not in course handoff")


def comparison_vessel_names(handoff: dict[str, Any]) -> set[str]:
    return {
        str(vessel)
        for comparison in handoff["comparisons"]
        for vessel in comparison["vessels"]
    }


def safe_vessel_path_name(vessel_name: str) -> str:
    if not vessel_name or Path(vessel_name).name != vessel_name:
        raise ConfigError(f"vessel {vessel_name} is not safe for artifact paths")
    return vessel_name


def handoff_task_ids(handoff: dict[str, Any]) -> set[str]:
    tasks = handoff["tasks"]
    if not isinstance(tasks, list):
        raise ConfigError("course handoff tasks must be a list")
    return {str(task["id"]) for task in tasks}


def write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
