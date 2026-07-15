from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yacht.logbook.io import write_json


RUN_INDEX_PATH = Path("run-index.json")
RUN_INDEX_SCHEMA = "yacht.run-index.v1"


def read_run_kind(logbook_dir: Path) -> str | None:
    from yacht.logbook.io import load_json_object

    index_path = logbook_dir / RUN_INDEX_PATH
    if not index_path.exists():
        return None
    index = load_json_object(index_path, "run index artifact")
    kind = index.get("run_kind")
    return str(kind) if kind is not None else None


def write_run_index(
    *,
    logbook_dir: Path,
    config_path: Path,
    run_kind: str,
    status: str,
    regatta: str,
    course: str,
    comparisons: Sequence[Any],
    artifacts: Mapping[str, str | Path],
) -> dict[str, Any]:
    index = build_run_index(
        logbook_dir=logbook_dir,
        config_path=config_path,
        run_kind=run_kind,
        status=status,
        regatta=regatta,
        course=course,
        comparisons=comparisons,
        artifacts=artifacts,
    )
    write_json(logbook_dir / RUN_INDEX_PATH, index)
    return index


def build_run_index(
    *,
    logbook_dir: Path,
    config_path: Path,
    run_kind: str,
    status: str,
    regatta: str,
    course: str,
    comparisons: Sequence[Any],
    artifacts: Mapping[str, str | Path],
) -> dict[str, Any]:
    return {
        "schema": RUN_INDEX_SCHEMA,
        "run_kind": run_kind,
        "status": status,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "config_path": str(config_path),
        "logbook": str(logbook_dir),
        "regatta": regatta,
        "course": course,
        "comparisons": [_comparison_to_json(comparison) for comparison in comparisons],
        "artifacts": {
            name: _artifact_to_json(logbook_dir, path)
            for name, path in artifacts.items()
        },
    }


def _comparison_to_json(comparison: Any) -> dict[str, Any]:
    if not isinstance(comparison, Mapping):
        return {
            "name": str(comparison.name),
            "course": str(comparison.course),
            "vessels": [str(vessel) for vessel in comparison.vessels],
        }
    return {
        "name": str(comparison["name"]),
        "course": str(comparison["course"]),
        "vessels": [str(vessel) for vessel in comparison["vessels"]],
    }


def _artifact_to_json(logbook_dir: Path, path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.is_absolute():
        artifact_path = logbook_dir / artifact_path
    return {
        "path": str(artifact_path),
        "present": artifact_path.exists(),
    }
