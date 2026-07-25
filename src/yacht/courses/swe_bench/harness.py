from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from yacht.domain.model import ConfigError


SWEBENCH_RUNNER_IMAGE = "yacht/swebench-runner:swebench-4.1.0"
DOCKER_SOCKET = "/var/run/docker.sock"
HF_CACHE_DIR = Path.home() / ".cache" / "yacht" / "swebench-hf"

CommandRunner = Callable[[list[str], Path], int]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = run_swe_bench_evaluation(
            predictions_path=args.predictions,
            report_dir=args.report_dir,
            dataset=args.dataset,
            split=args.split,
            run_id=args.run_id,
            vessel_name=args.vessel,
            max_workers=args.max_workers,
            instance_ids=args.instance_ids,
        )
    except ConfigError as error:
        print(f"swe-bench harness error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yacht.courses.swe_bench.harness",
        description=(
            "Run the official SWE-bench evaluation in the pinned runner "
            "container and leave the native report in the report directory."
        ),
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--vessel", required=True)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--instance-ids", nargs="+", required=True)
    return parser.parse_args(argv)


def run_swe_bench_evaluation(
    *,
    predictions_path: Path,
    report_dir: Path,
    dataset: str,
    split: str,
    run_id: str,
    vessel_name: str,
    max_workers: int,
    instance_ids: list[str],
    command_runner: CommandRunner | None = None,
    runner_image: str = SWEBENCH_RUNNER_IMAGE,
) -> dict[str, object]:
    if not predictions_path.exists():
        raise ConfigError(f"candidate predictions file not found: {predictions_path}")
    report_dir.mkdir(parents=True, exist_ok=True)
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    command = evaluator_command(
        predictions_path=predictions_path,
        report_dir=report_dir,
        dataset=dataset,
        split=split,
        run_id=run_id,
        max_workers=max_workers,
        instance_ids=instance_ids,
        runner_image=runner_image,
    )
    runner = command_runner if command_runner is not None else _run_command
    exit_code = runner(command, report_dir)
    if exit_code != 0:
        raise ConfigError(f"swe-bench evaluation failed with exit code {exit_code}")

    report_path = report_dir / f"{vessel_name}.{run_id}.json"
    if not report_path.exists():
        raise ConfigError(
            f"swe-bench evaluation completed but the native report is "
            f"missing: {report_path}"
        )
    return {
        "status": "complete",
        "vessel": vessel_name,
        "run_id": run_id,
        "native_report_path": str(report_path),
    }


def evaluator_command(
    *,
    predictions_path: Path,
    report_dir: Path,
    dataset: str,
    split: str,
    run_id: str,
    max_workers: int,
    instance_ids: list[str],
    runner_image: str = SWEBENCH_RUNNER_IMAGE,
) -> list[str]:
    predictions_dir = predictions_path.parent
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{DOCKER_SOCKET}:{DOCKER_SOCKET}",
        "-v",
        f"{predictions_dir}:{predictions_dir}",
        "-v",
        f"{report_dir}:{report_dir}",
        "-v",
        f"{HF_CACHE_DIR}:{HF_CACHE_DIR}",
        "-e",
        f"HF_HOME={HF_CACHE_DIR}",
        "-w",
        str(report_dir),
        runner_image,
        "python",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset,
        "--split",
        split,
        "--predictions_path",
        str(predictions_path),
        "--max_workers",
        str(max_workers),
        "--run_id",
        run_id,
        "--report_dir",
        str(report_dir),
        "--instance_ids",
        *instance_ids,
    ]


def _run_command(argv: list[str], cwd: Path) -> int:
    cwd.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(argv, cwd=cwd)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
