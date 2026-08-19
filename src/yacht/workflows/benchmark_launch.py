from __future__ import annotations

import json
import subprocess
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Callable

from yacht.courses.registry import course_adapter_block
from yacht.workflows.benchmark_launcher_handoff import BENCHMARK_LAUNCHER_HANDOFF_PATH
from yacht.reports.next_steps import command_step
from yacht.preflight import CommandResult
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import BENCHMARK_LAUNCH_RESULT_SCHEMA
from yacht.contracts.schemas import validate_benchmark_launch_result_document
from yacht.runtimes.process import subprocess_env


BENCHMARK_LAUNCH_RESULT_PATH = Path("benchmark-launch-result.json")
CommandRunner = Callable[[list[str], Path], CommandResult]


def write_benchmark_launch_result(
    *,
    logbook_dir: Path,
    command_runner: CommandRunner | None = None,
    secret_env_by_vessel: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Run each ready vessel's native launcher command.

    ``secret_env_by_vessel`` reintroduces the source environment
    variables for the secrets a vessel declares (see
    :func:`yacht.runtimes.secrets.secret_env_by_vessel`). Yacht scrubs
    resolved ``@env:`` variables from its own environment, so a launcher
    that forwards a variable by name (``docker run -e NAME``) only sees
    the value when it is reintroduced here.
    """
    launcher_handoff = _load_launcher_handoff(logbook_dir)
    result = _build_launch_result(
        logbook_dir,
        launcher_handoff,
        command_runner,
        secret_env_by_vessel or {},
    )
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
    command_runner: CommandRunner | None,
    secret_env_by_vessel: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    comparisons = [
        _comparison_result(
            logbook_dir, comparison, command_runner, secret_env_by_vessel
        )
        for comparison in launcher_handoff["comparisons"]
    ]
    summary = _summary(comparisons)
    return {
        "schema": BENCHMARK_LAUNCH_RESULT_SCHEMA,
        "regatta": str(launcher_handoff["regatta"]),
        "course": str(launcher_handoff["course"]),
        "adapter": course_adapter_block(launcher_handoff["adapter"]),
        "status": _status(summary),
        "summary": summary,
        "next_steps": _next_steps(logbook_dir, summary),
        "comparisons": comparisons,
    }


def _comparison_result(
    logbook_dir: Path,
    comparison: dict[str, Any],
    command_runner: CommandRunner | None,
    secret_env_by_vessel: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    vessels = [
        _vessel_result(
            logbook_dir=logbook_dir,
            comparison_name=str(comparison["name"]),
            vessel=vessel,
            command_runner=command_runner,
            secret_env=secret_env_by_vessel.get(str(vessel["name"]), {}),
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
    command_runner: CommandRunner | None,
    secret_env: Mapping[str, str],
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
    if command_runner is None:
        result = _run_command(command, native_report_dir, secret_env)
    else:
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
    vessels = [vessel for comparison in comparisons for vessel in comparison["vessels"]]
    return {
        "total_vessels": len(vessels),
        "launched_vessels": sum(
            1 for vessel in vessels if vessel["status"] in {"completed", "failed"}
        ),
        "completed_launches": sum(
            1 for vessel in vessels if vessel["status"] == "completed"
        ),
        "failed_launches": sum(1 for vessel in vessels if vessel["status"] == "failed"),
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


def _next_steps(logbook_dir: Path, summary: dict[str, int]) -> list[dict[str, object]]:
    if summary["failed_launches"]:
        return [
            command_step(
                label="Inspect launch stderr",
                reason=(
                    "One or more native benchmark launches failed; inspect the "
                    "stderr paths in this artifact before collecting grading."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "internals",
                    "benchmark-launch",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        ]
    if summary["launched_vessels"] == 0:
        return [
            command_step(
                label="Review benchmark readiness",
                reason=(
                    "No vessels were ready to launch; inspect blocked inputs before "
                    "running the native benchmark harness."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "internals",
                    "benchmark-plan",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
        ]
    return [
        command_step(
            label="Collect benchmark grading",
            reason=(
                "Native launches completed; validate the SWE-bench reports and "
                "write YACHT grading artifacts next."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "internals",
                "benchmark-collect-grading",
                "<regatta.toml>",
                "--logbook",
                str(logbook_dir),
            ],
        )
    ]


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


def _run_command(
    argv: list[str],
    cwd: Path,
    secret_env: Mapping[str, str],
) -> CommandResult:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=subprocess_env(tuple(argv), dict(secret_env)),
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
