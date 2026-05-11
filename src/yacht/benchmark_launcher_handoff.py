from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from yacht.course_handoff import COURSE_HANDOFF_PATH
from yacht.regatta import ConfigError
from yacht.schemas import (
    BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
    validate_benchmark_launcher_handoff_document,
)
from yacht.swebench_artifacts import candidate_patches_path, grading_report_path
from yacht.swebench_artifacts import vessel_artifact_dir


BENCHMARK_LAUNCHER_HANDOFF_PATH = Path("benchmark-launcher-handoff.json")


def write_benchmark_launcher_handoff(
    *,
    logbook_dir: Path,
    max_workers: int = 1,
    python_executable: str = "python",
) -> dict[str, Any]:
    if max_workers < 1:
        raise ConfigError("max_workers must be an integer >= 1")
    python_command = shlex.split(python_executable)
    if not python_command:
        raise ConfigError("python_executable must be non-empty")

    handoff = _load_handoff(logbook_dir)
    launcher_handoff = _build_launcher_handoff(
        logbook_dir=logbook_dir,
        handoff=handoff,
        max_workers=max_workers,
        python_command=python_command,
    )
    validate_benchmark_launcher_handoff_document(launcher_handoff)
    _write_json(logbook_dir / BENCHMARK_LAUNCHER_HANDOFF_PATH, launcher_handoff)
    return launcher_handoff


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


def _build_launcher_handoff(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    max_workers: int,
    python_command: list[str],
) -> dict[str, Any]:
    comparisons = [
        _comparison_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison=comparison,
            max_workers=max_workers,
            python_command=python_command,
        )
        for comparison in handoff["comparisons"]
    ]
    return {
        "schema": BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
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
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    comparison: dict[str, Any],
    max_workers: int,
    python_command: list[str],
) -> dict[str, Any]:
    vessels = [
        _vessel_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison_name=str(comparison["name"]),
            vessel_name=str(vessel_name),
            max_workers=max_workers,
            python_command=python_command,
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
    max_workers: int,
    python_command: list[str],
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
    status = _vessel_status(candidate_present, grading_present)
    vessel = {
        "name": vessel_name,
        "status": status,
        "candidate_patches_path": str(candidate_path),
        "candidate_patches_present": candidate_present,
        "expected_yacht_grading_report_path": str(grading_path),
        "grading_report_present": grading_present,
        "native_report_dir": str(
            vessel_artifact_dir(
                logbook_dir=logbook_dir,
                handoff=handoff,
                vessel_name=vessel_name,
            )
            / "native-report"
        ),
    }
    if status == "ready-to-launch":
        command = _swe_bench_command(
            handoff=handoff,
            candidate_path=candidate_path,
            comparison_name=comparison_name,
            vessel_name=vessel_name,
            native_report_dir=Path(str(vessel["native_report_dir"])),
            max_workers=max_workers,
            python_command=python_command,
        )
        vessel["command"] = command
        vessel["command_preview"] = shlex.join(command)
    return vessel


def _swe_bench_command(
    *,
    handoff: dict[str, Any],
    candidate_path: Path,
    comparison_name: str,
    vessel_name: str,
    native_report_dir: Path,
    max_workers: int,
    python_command: list[str],
) -> list[str]:
    return [
        *python_command,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        str(handoff["adapter"]["dataset"]),
        "--split",
        str(handoff["adapter"]["split"]),
        "--predictions_path",
        str(candidate_path),
        "--max_workers",
        str(max_workers),
        "--run_id",
        _run_id(
            regatta=str(handoff["regatta"]),
            comparison_name=comparison_name,
            vessel_name=vessel_name,
        ),
        "--report_dir",
        str(native_report_dir),
        "--instance_ids",
        *[str(task["id"]) for task in handoff["tasks"]],
    ]


def _run_id(*, regatta: str, comparison_name: str, vessel_name: str) -> str:
    return "__".join(
        value.replace("/", "__").replace(" ", "_")
        for value in (regatta, comparison_name, vessel_name)
    )


def _vessel_status(candidate_present: bool, grading_present: bool) -> str:
    if grading_present:
        return "already-graded"
    if candidate_present:
        return "ready-to-launch"
    return "missing-candidate-patches"


def _aggregate_status(statuses: list[str]) -> str:
    if all(status in {"already-graded", "complete"} for status in statuses):
        return "complete"
    if all(status == "ready-to-launch" for status in statuses):
        return "ready-to-launch"
    if all(
        status in {"missing-candidate-patches", "missing-inputs"}
        for status in statuses
    ):
        return "missing-inputs"
    return "mixed"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
