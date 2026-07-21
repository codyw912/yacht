from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError


LCB_RUNNER_IMAGE = "yacht/lcb-runner:lcb-28fef95"
NATIVE_REPORT_SCHEMA_VERSION = 1

CommandRunner = Callable[[list[str], Path], int]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = run_livecodebench_evaluation(
            candidates_path=args.candidates,
            window_path=args.window_file,
            work_dir=args.work_dir,
            report_dir=args.report_dir,
            run_id=args.run_id,
            vessel_name=args.vessel,
            release_version=args.release_version,
            start_date=args.start_date,
            end_date=args.end_date,
            launcher_image=args.launcher_image,
        )
    except ConfigError as error:
        print(f"livecodebench harness error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yacht.courses.livecodebench.harness",
        description=(
            "Run the official LiveCodeBench custom evaluator over yacht "
            "candidate records and write the normalized native report."
        ),
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--window-file", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--vessel", required=True)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--launcher-image", default=LCB_RUNNER_IMAGE)
    return parser.parse_args(argv)


def run_livecodebench_evaluation(
    *,
    candidates_path: Path,
    window_path: Path,
    work_dir: Path,
    report_dir: Path,
    run_id: str,
    vessel_name: str,
    release_version: str,
    start_date: str | None,
    end_date: str | None,
    launcher_image: str = LCB_RUNNER_IMAGE,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    candidates = _load_candidates(candidates_path)
    window_ids = _load_window_ids(window_path)
    unknown = sorted(set(candidates) - set(window_ids))
    if unknown:
        raise ConfigError(
            "candidate records contain question ids outside the window: "
            + ", ".join(unknown)
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    outputs_path = work_dir / "custom-outputs.json"
    outputs = [
        {"question_id": question_id, "code_list": [candidates.get(question_id, "")]}
        for question_id in window_ids
    ]
    outputs_path.write_text(
        json.dumps(outputs, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runner = command_runner if command_runner is not None else _run_command
    command = evaluator_command(
        outputs_path,
        work_dir=work_dir,
        release_version=release_version,
        start_date=start_date,
        end_date=end_date,
        launcher_image=launcher_image,
    )
    exit_code = runner(command, work_dir)
    if exit_code != 0:
        raise ConfigError(f"livecodebench evaluation failed with exit code {exit_code}")

    graded = _graded_by_question(
        work_dir / "custom-outputs_codegeneration_output_eval_all.json"
    )
    report = native_report_from_graded(
        graded_by_question=graded,
        submitted_ids=sorted(candidates),
        window_ids=window_ids,
        release_version=release_version,
        start_date=start_date,
        end_date=end_date,
    )
    report_path = report_dir / f"{vessel_name}.{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "complete",
        "vessel": vessel_name,
        "run_id": run_id,
        "native_report_path": str(report_path),
        "submitted_instances": report["submitted_instances"],
        "resolved_instances": report["resolved_instances"],
        "padding_instances": report["padding_instances"],
    }


def evaluator_command(
    outputs_path: Path,
    *,
    work_dir: Path,
    release_version: str,
    start_date: str | None,
    end_date: str | None,
    launcher_image: str = LCB_RUNNER_IMAGE,
) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{work_dir}:{work_dir}",
        "-e",
        f"HF_HOME={work_dir}/hf-cache",
        launcher_image,
        "python",
        "-m",
        "lcb_runner.runner.custom_evaluator",
        "--scenario",
        "codegeneration",
        "--release_version",
        release_version,
        "--custom_output_file",
        str(outputs_path),
    ]
    if start_date is not None:
        command.extend(["--start_date", start_date])
    if end_date is not None:
        command.extend(["--end_date", end_date])
    return command


def native_report_from_graded(
    *,
    graded_by_question: dict[str, bool],
    submitted_ids: list[str],
    window_ids: list[str],
    release_version: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    missing = sorted(set(submitted_ids) - set(graded_by_question))
    if missing:
        raise ConfigError(
            "livecodebench evaluation output is missing submitted questions: "
            + ", ".join(missing)
        )
    resolved_ids = [
        question_id for question_id in submitted_ids if graded_by_question[question_id]
    ]
    unresolved_ids = [
        question_id
        for question_id in submitted_ids
        if not graded_by_question[question_id]
    ]
    return {
        "schema_version": NATIVE_REPORT_SCHEMA_VERSION,
        "total_instances": len(submitted_ids),
        "submitted_instances": len(submitted_ids),
        "completed_instances": len(submitted_ids),
        "resolved_instances": len(resolved_ids),
        "unresolved_instances": len(unresolved_ids),
        "empty_patch_instances": 0,
        "error_instances": 0,
        "submitted_ids": list(submitted_ids),
        "completed_ids": list(submitted_ids),
        "incomplete_ids": [],
        "resolved_ids": resolved_ids,
        "unresolved_ids": unresolved_ids,
        "empty_patch_ids": [],
        "error_ids": [],
        "padding_instances": len(window_ids) - len(submitted_ids),
        "livecodebench": {
            "release_version": release_version,
            "start_date": start_date,
            "end_date": end_date,
            "window_instances": len(window_ids),
        },
    }


def _graded_by_question(eval_all_path: Path) -> dict[str, bool]:
    payload = _load_json(eval_all_path, "livecodebench evaluation output")
    if not isinstance(payload, list):
        raise ConfigError("livecodebench evaluation output must be a JSON array")
    graded: dict[str, bool] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            raise ConfigError(
                "livecodebench evaluation output entries must be JSON objects"
            )
        question_id = entry.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ConfigError(
                "livecodebench evaluation output entry is missing question_id"
            )
        graded_list = entry.get("graded_list")
        if not isinstance(graded_list, list) or not graded_list:
            graded[question_id] = False
            continue
        graded[question_id] = graded_list[0] is True
    return graded


def _load_candidates(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigError(f"candidate records file not found: {path}")
    candidates: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ConfigError(
                f"candidate records line {line_number} is not valid JSON: {error}"
            ) from error
        if not isinstance(record, dict):
            raise ConfigError(
                f"candidate records line {line_number} must be a JSON object"
            )
        question_id = record.get("instance_id")
        code = record.get("code")
        if not isinstance(question_id, str) or not question_id:
            raise ConfigError(
                f"candidate records line {line_number}.instance_id must be non-empty"
            )
        if not isinstance(code, str):
            raise ConfigError(
                f"candidate records line {line_number}.code must be a string"
            )
        if question_id in candidates:
            raise ConfigError(
                f"candidate records contain duplicate question {question_id}"
            )
        candidates[question_id] = code
    if not candidates:
        raise ConfigError("candidate records must contain at least one record")
    return candidates


def _load_window_ids(path: Path) -> list[str]:
    payload = _load_json(path, "livecodebench window file")
    if (
        not isinstance(payload, list)
        or not payload
        or not all(isinstance(item, str) and item for item in payload)
    ):
        raise ConfigError(
            "livecodebench window file must be a non-empty JSON array of question ids"
        )
    return sorted(payload)


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error


def _run_command(argv: list[str], cwd: Path) -> int:
    cwd.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(argv, cwd=cwd)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
