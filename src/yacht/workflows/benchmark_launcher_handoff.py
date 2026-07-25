from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.registry import command_preview
from yacht.courses.registry import course_adapter_block
from yacht.courses.registry import evaluator_adapter
from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.preflight.gate import PreflightGate, preflight_gate
from yacht.domain.model import ConfigError
from yacht.runtimes.snapshot_gate import RuntimeSnapshotGate, runtime_snapshot_gate
from yacht.contracts.schemas import (
    BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
    SchemaValidationError,
    validate_benchmark_launcher_handoff_document,
)
from yacht.courses.artifacts import (
    candidate_patches_path,
    grading_report_path,
)
from yacht.courses.artifacts import vessel_artifact_dir


BENCHMARK_LAUNCHER_HANDOFF_PATH = Path("benchmark-launcher-handoff.json")


def native_report_path_from_launcher_handoff(
    *,
    logbook_dir: Path,
    vessel_name: str,
) -> Path:
    launcher_path = logbook_dir / BENCHMARK_LAUNCHER_HANDOFF_PATH
    if not launcher_path.exists():
        raise ConfigError(
            f"benchmark launcher handoff artifact not found: {launcher_path}"
        )

    launcher_handoff = _load_json_object(
        launcher_path,
        "benchmark launcher handoff artifact",
    )
    try:
        validate_benchmark_launcher_handoff_document(launcher_handoff)
    except SchemaValidationError as error:
        raise ConfigError(str(error)) from error

    matches = [
        vessel
        for comparison in launcher_handoff["comparisons"]
        for vessel in comparison["vessels"]
        if vessel["name"] == vessel_name
    ]
    if not matches:
        raise ConfigError(
            f"benchmark launcher handoff does not contain vessel {vessel_name}"
        )
    if len(matches) > 1:
        raise ConfigError(
            "benchmark launcher handoff contains multiple entries for vessel "
            f"{vessel_name}; pass --input explicitly"
        )

    vessel = matches[0]
    native_report_path = vessel.get("expected_native_report_path")
    if isinstance(native_report_path, str) and native_report_path:
        path = Path(native_report_path)
        if not path.exists():
            adapter = evaluator_adapter(str(launcher_handoff["adapter"]["kind"]))
            raise ConfigError(f"native {adapter.display_name} report not found: {path}")
        return path

    command = vessel.get("command")
    if command is None:
        raise ConfigError(
            "benchmark launcher handoff does not include a launch command for "
            f"vessel {vessel_name}; pass --input explicitly"
        )
    run_id = _command_option_value(command, "--run-id", vessel_name)
    adapter = evaluator_adapter(str(launcher_handoff["adapter"]["kind"]))
    native_report_path = Path(
        str(vessel["native_report_dir"])
    ) / adapter.native_report_filename(
        vessel_name=vessel_name,
        run_id=run_id,
    )
    if not native_report_path.exists():
        raise ConfigError(
            f"native {adapter.display_name} report not found: {native_report_path}"
        )
    return native_report_path


def write_benchmark_launcher_handoff(
    *,
    logbook_dir: Path,
    max_workers: int = 1,
) -> dict[str, Any]:
    if max_workers < 1:
        raise ConfigError("max_workers must be an integer >= 1")

    handoff = _load_handoff(logbook_dir)
    launcher_handoff = _build_launcher_handoff(
        logbook_dir=logbook_dir,
        handoff=handoff,
        max_workers=max_workers,
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
) -> dict[str, Any]:
    comparisons = [
        _comparison_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison=comparison,
            max_workers=max_workers,
        )
        for comparison in handoff["comparisons"]
    ]
    return {
        "schema": BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
        "regatta": str(handoff["regatta"]),
        "course": str(handoff["course"]),
        "adapter": {
            **course_adapter_block(handoff["adapter"]),
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
) -> dict[str, Any]:
    vessels = [
        _vessel_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison_name=str(comparison["name"]),
            vessel_name=str(vessel_name),
            max_workers=max_workers,
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
    status = _vessel_status(
        candidate_present=candidate_present,
        grading_present=grading_present,
        gate=gate,
        snapshot_gate=snapshot_gate,
    )
    native_report_dir = (
        vessel_artifact_dir(
            logbook_dir=logbook_dir,
            handoff=handoff,
            vessel_name=vessel_name,
        )
        / "native-report"
    )
    run_id = _run_id(
        regatta=str(handoff["regatta"]),
        comparison_name=comparison_name,
        vessel_name=vessel_name,
    )
    adapter = evaluator_adapter(str(handoff["adapter"]["kind"]))
    vessel = {
        "name": vessel_name,
        "status": status,
        "candidate_patches_path": str(candidate_path),
        "candidate_patches_present": candidate_present,
        "expected_yacht_grading_report_path": str(grading_path),
        "grading_report_present": grading_present,
        "preflight_artifact_path": str(gate.artifact_path),
        "preflight_artifact_present": gate.artifact_present,
        "preflight_status": gate.status,
        "runtime_instances_artifact_path": str(snapshot_gate.artifact_path),
        "runtime_instances_artifact_present": snapshot_gate.artifact_present,
        "runtime_snapshot_status": snapshot_gate.status,
        "native_report_dir": str(native_report_dir),
        "expected_native_report_path": str(
            native_report_dir
            / adapter.native_report_filename(vessel_name=vessel_name, run_id=run_id)
        ),
    }
    if status == "ready-to-launch":
        command = adapter.launcher_command(
            course_adapter=handoff["adapter"],
            tasks=handoff["tasks"],
            candidate_path=candidate_path,
            native_report_dir=Path(str(vessel["native_report_dir"])),
            run_id=run_id,
            vessel_name=vessel_name,
            max_workers=max_workers,
        )
        vessel["command"] = command
        vessel["command_preview"] = command_preview(command)
    return vessel


def _run_id(*, regatta: str, comparison_name: str, vessel_name: str) -> str:
    return "__".join(
        value.replace("/", "__").replace(" ", "_")
        for value in (regatta, comparison_name, vessel_name)
    )


def _command_option_value(
    command: object,
    option: str,
    vessel_name: str,
) -> str:
    if not isinstance(command, list):
        raise ConfigError(
            "benchmark launcher handoff launch command for vessel "
            f"{vessel_name} must be a list"
        )
    for index, value in enumerate(command):
        if value == option:
            if index + 1 >= len(command) or not isinstance(command[index + 1], str):
                raise ConfigError(
                    "benchmark launcher handoff launch command for vessel "
                    f"{vessel_name} is missing a value for {option}"
                )
            return command[index + 1]
    raise ConfigError(
        "benchmark launcher handoff launch command for vessel "
        f"{vessel_name} is missing {option}"
    )


def _vessel_status(
    *,
    candidate_present: bool,
    grading_present: bool,
    gate: PreflightGate,
    snapshot_gate: RuntimeSnapshotGate,
) -> str:
    if grading_present:
        return "already-graded"
    if not candidate_present:
        return "missing-candidate-patches"
    if not gate.artifact_present:
        return "missing-preflight"
    if not gate.passed:
        return "preflight-failed"
    if not snapshot_gate.matched:
        return "missing-runtime-snapshot"
    return "ready-to-launch"


def _aggregate_status(statuses: list[str]) -> str:
    if all(status in {"already-graded", "complete"} for status in statuses):
        return "complete"
    if all(status == "ready-to-launch" for status in statuses):
        return "ready-to-launch"
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
