from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from yacht.benchmark_launcher_handoff import BENCHMARK_LAUNCHER_HANDOFF_PATH
from yacht.preflight import CommandResult
from yacht.regatta import ConfigError
from yacht.schemas import BENCHMARK_LAUNCH_RESULT_SCHEMA
from yacht.schemas import validate_benchmark_launch_result_document


BENCHMARK_LAUNCH_RESULT_PATH = Path("benchmark-launch-result.json")
CommandRunner = Callable[[list[str], Path], CommandResult]


def write_benchmark_launch_result(
    *,
    logbook_dir: Path,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    launcher_handoff = _load_launcher_handoff(logbook_dir)
    runner = command_runner if command_runner is not None else _run_command
    result = _build_launch_result(logbook_dir, launcher_handoff, runner)
    validate_benchmark_launch_result_document(result)
    _write_json(logbook_dir / BENCHMARK_LAUNCH_RESULT_PATH, result)
    return result


def _load_launcher_handoff(logbook_dir: Path) -> dict[str, Any]:
    path = logbook_dir / BENCHMARK_LAUNCHER_HANDOFF_PATH
    if not path.exists():
        raise ConfigError(f"benchmark launcher handoff artifact not found: {path}")
    return _load_json_object(path, "benchmark launcher handoff artifact")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _build_launch_result(
    logbook_dir: Path,
    launcher_handoff: dict[str, Any],
    command_runner: CommandRunner,
) -> dict[str, Any]:
    comparisons = [
        _comparison_result(logbook_dir, comparison, command_runner)
        for comparison in launcher_handoff["comparisons"]
    ]
    summary = _summary(comparisons)
    return {
        "schema": BENCHMARK_LAUNCH_RESULT_SCHEMA,
        "regatta": str(launcher_handoff["regatta"]),
        "course": str(launcher_handoff["course"]),
        "adapter": {
            "kind": str(launcher_handoff["adapter"]["kind"]),
            "dataset": str(launcher_handoff["adapter"]["dataset"]),
            "split": str(launcher_handoff["adapter"]["split"]),
            "harness": str(launcher_handoff["adapter"]["harness"]),
        },
        "status": _status(summary),
        "summary": summary,
        "comparisons": comparisons,
    }


def _comparison_result(
    logbook_dir: Path,
    comparison: dict[str, Any],
    command_runner: CommandRunner,
) -> dict[str, Any]:
    vessels = [
        _vessel_result(
            logbook_dir=logbook_dir,
            comparison_name=str(comparison["name"]),
            vessel=vessel,
            command_runner=command_runner,
        )
        for vessel in comparison["vessels"]
    ]
    return {
        "name": str(comparison["name"]),
        "course": str(comparison["course"]),
        "status": _comparison_status(vessels),
        "vessels": vessels,
    }


def _vessel_result(
    *,
    logbook_dir: Path,
    comparison_name: str,
    vessel: dict[str, Any],
    command_runner: CommandRunner,
) -> dict[str, Any]:
    if vessel["status"] != "ready-to-launch":
        return {
            "name": str(vessel["name"]),
            "status": "skipped",
            "launcher_status": str(vessel["status"]),
            "skipped_reason": str(vessel["status"]),
        }
    command = _command(vessel)
    output_dir = (
        logbook_dir / "benchmark-launch" / comparison_name / str(vessel["name"])
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    native_report_dir = Path(str(vessel["native_report_dir"]))
    native_report_dir.mkdir(parents=True, exist_ok=True)
    result = command_runner(command, native_report_dir)
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return {
        "name": str(vessel["name"]),
        "status": "completed" if result.exit_code == 0 else "failed",
        "launcher_status": str(vessel["status"]),
        "command": command,
        "command_preview": str(vessel["command_preview"]),
        "exit_code": result.exit_code,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "native_report_dir": str(native_report_dir),
        "expected_native_report_path": str(vessel["expected_native_report_path"]),
        "expected_yacht_grading_report_path": str(
            vessel["expected_yacht_grading_report_path"]
        ),
    }


def _command(vessel: dict[str, Any]) -> list[str]:
    command = vessel.get("command")
    if not isinstance(command, list) or not all(
        isinstance(item, str) and item for item in command
    ):
        raise ConfigError(
            "ready benchmark launcher vessel must include a non-empty command"
        )
    return command


def _summary(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    vessels = [
        vessel for comparison in comparisons for vessel in comparison["vessels"]
    ]
    return {
        "total_vessels": len(vessels),
        "launched_vessels": sum(
            1 for vessel in vessels if vessel["status"] in {"completed", "failed"}
        ),
        "completed_launches": sum(
            1 for vessel in vessels if vessel["status"] == "completed"
        ),
        "failed_launches": sum(
            1 for vessel in vessels if vessel["status"] == "failed"
        ),
        "skipped_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "skipped"
        ),
    }


def _status(summary: dict[str, int]) -> str:
    if summary["failed_launches"]:
        return "failed"
    if summary["launched_vessels"] == 0:
        return "blocked"
    if summary["skipped_vessels"]:
        return "partial"
    return "complete"


def _comparison_status(vessels: list[dict[str, Any]]) -> str:
    return _status(
        {
            "launched_vessels": sum(
                1 for vessel in vessels if vessel["status"] in {"completed", "failed"}
            ),
            "failed_launches": sum(
                1 for vessel in vessels if vessel["status"] == "failed"
            ),
            "skipped_vessels": sum(
                1 for vessel in vessels if vessel["status"] == "skipped"
            ),
        }
    )


def _run_command(argv: list[str], cwd: Path) -> CommandResult:
    result = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
