from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError


HARBOR_REQUIREMENT = "harbor==0.20.0"
LITELLM_REQUIREMENT = "litellm==1.91.3"
HARBOR_JOB_NAME = "harbor"
NATIVE_REPORT_SCHEMA_VERSION = 1

CommandRunner = Callable[[list[str], Path], int]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = run_terminal_bench_job(
            job_path=args.job,
            roster_path=args.roster,
            trials_dir=args.trials_dir,
            report_dir=args.report_dir,
            run_id=args.run_id,
            vessel_name=args.vessel,
        )
    except ConfigError as error:
        print(f"terminal-bench harness error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yacht.courses.terminal_bench.harness",
        description=(
            "Run a rendered terminal-bench job through Harbor and write the "
            "normalized native report."
        ),
    )
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--trials-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--vessel", required=True)
    return parser.parse_args(argv)


def run_terminal_bench_job(
    *,
    job_path: Path,
    roster_path: Path,
    trials_dir: Path,
    report_dir: Path,
    run_id: str,
    vessel_name: str,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    job = _load_job(job_path)
    roster_ids = _load_roster_ids(roster_path)
    harbor_config_path = trials_dir / "harbor-run-config.json"
    _write_json(harbor_config_path, harbor_run_config(job, trials_dir=trials_dir))

    runner = command_runner if command_runner is not None else _run_command
    command = harbor_command(harbor_config_path)
    exit_code = runner(command, trials_dir)
    if exit_code != 0:
        raise ConfigError(f"harbor run failed with exit code {exit_code}")

    report = native_report_from_trials(
        trials_dir=trials_dir,
        roster_ids=roster_ids,
    )
    report_path = report_dir / f"{vessel_name}.{run_id}.json"
    _write_json(report_path, report)
    return {
        "status": "complete",
        "vessel": vessel_name,
        "run_id": run_id,
        "harbor_config_path": str(harbor_config_path),
        "native_report_path": str(report_path),
        "submitted_instances": report["submitted_instances"],
        "resolved_instances": report["resolved_instances"],
    }


def harbor_command(harbor_config_path: Path) -> list[str]:
    return [
        "uv",
        "run",
        "--with",
        HARBOR_REQUIREMENT,
        "--with",
        LITELLM_REQUIREMENT,
        "harbor",
        "run",
        "-c",
        str(harbor_config_path),
        "--yes",
        "--quiet",
    ]


def harbor_run_config(job: dict[str, Any], *, trials_dir: Path) -> dict[str, Any]:
    agent = job["agent"]
    agent_config: dict[str, Any] = {
        "name": str(agent["name"]),
        "model_name": str(agent["model"]),
        "kwargs": {"version": str(agent["version"])},
    }
    if agent.get("env"):
        agent_config["env"] = dict(agent["env"])
    if agent.get("mcp_servers"):
        agent_config["mcp_servers"] = [
            {"transport": "stdio", **dict(server)} for server in agent["mcp_servers"]
        ]
    dataset = job["dataset"]
    return {
        "jobs_dir": str(trials_dir),
        "job_name": HARBOR_JOB_NAME,
        "agents": [agent_config],
        "datasets": [
            {
                "name": str(dataset["name"]),
                "version": str(dataset["version"]),
                "task_names": [str(task) for task in job["tasks"]],
            }
        ],
        "n_attempts": 1,
    }


def native_report_from_trials(
    *,
    trials_dir: Path,
    roster_ids: list[str],
) -> dict[str, Any]:
    trials = collect_trial_results(trials_dir)
    trials_by_task: dict[str, dict[str, Any]] = {}
    for trial in trials:
        task_name = str(trial["task_name"])
        if task_name in trials_by_task:
            raise ConfigError(
                f"terminal-bench trials contain multiple results for task {task_name}"
            )
        trials_by_task[task_name] = trial

    unexpected = sorted(set(trials_by_task) - set(roster_ids))
    if unexpected:
        raise ConfigError(
            "terminal-bench trials contain tasks outside the roster: "
            + ", ".join(unexpected)
        )

    completed_ids = []
    resolved_ids = []
    unresolved_ids = []
    error_ids = []
    incomplete_ids = []
    for task_id in roster_ids:
        trial = trials_by_task.get(task_id)
        if trial is None:
            incomplete_ids.append(task_id)
            continue
        if trial.get("exception") is not None:
            error_ids.append(task_id)
            continue
        reward = trial.get("reward")
        if reward is None:
            error_ids.append(task_id)
            continue
        completed_ids.append(task_id)
        if float(reward) >= 1.0:
            resolved_ids.append(task_id)
        else:
            unresolved_ids.append(task_id)

    return {
        "schema_version": NATIVE_REPORT_SCHEMA_VERSION,
        "total_instances": len(roster_ids),
        "submitted_instances": len(roster_ids),
        "completed_instances": len(completed_ids),
        "resolved_instances": len(resolved_ids),
        "unresolved_instances": len(unresolved_ids),
        "empty_patch_instances": 0,
        "error_instances": len(error_ids),
        "submitted_ids": list(roster_ids),
        "completed_ids": completed_ids,
        "incomplete_ids": incomplete_ids,
        "resolved_ids": resolved_ids,
        "unresolved_ids": unresolved_ids,
        "empty_patch_ids": [],
        "error_ids": error_ids,
        "trials": trials,
    }


def collect_trial_results(trials_dir: Path) -> list[dict[str, Any]]:
    result_paths = sorted((trials_dir / HARBOR_JOB_NAME).glob("*/result.json"))
    return [_trial_summary(path) for path in result_paths]


def _trial_summary(result_path: Path) -> dict[str, Any]:
    result = _load_json_object(result_path, "terminal-bench trial result")
    task_name = result.get("task_name")
    if not isinstance(task_name, str) or not task_name:
        raise ConfigError(
            f"terminal-bench trial result {result_path} is missing task_name"
        )
    agent_info = result.get("agent_info")
    agent: dict[str, Any] = {}
    if isinstance(agent_info, dict):
        agent = {
            "name": agent_info.get("name"),
            "version": agent_info.get("version"),
            "model": _model_name(agent_info),
        }
    summary: dict[str, Any] = {
        "task_name": task_name,
        "trial_name": result.get("trial_name"),
        "trial_dir": str(result_path.parent),
        "agent": agent,
        "reward": _trial_reward(result),
        "exception": _trial_exception(result),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
    }
    usage = _trial_usage(result)
    if usage is not None:
        summary["usage"] = usage
    return summary


def _model_name(agent_info: dict[str, Any]) -> str | None:
    model_info = agent_info.get("model_info")
    if isinstance(model_info, dict):
        name = model_info.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _trial_reward(result: dict[str, Any]) -> float | None:
    verifier_result = result.get("verifier_result")
    if not isinstance(verifier_result, dict):
        return None
    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, dict) or not rewards:
        return None
    if "reward" in rewards:
        value = rewards["reward"]
    elif len(rewards) == 1:
        value = next(iter(rewards.values()))
    else:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _trial_exception(result: dict[str, Any]) -> dict[str, str] | None:
    exception_info = result.get("exception_info")
    if not isinstance(exception_info, dict):
        return None
    return {
        "type": str(exception_info.get("exception_type")),
        "message": str(exception_info.get("exception_message")),
    }


def _trial_usage(result: dict[str, Any]) -> dict[str, Any] | None:
    agent_result = result.get("agent_result")
    if not isinstance(agent_result, dict):
        return None
    usage = {
        key: agent_result.get(field)
        for key, field in (
            ("input_tokens", "n_input_tokens"),
            ("cache_tokens", "n_cache_tokens"),
            ("output_tokens", "n_output_tokens"),
            ("cost_usd", "cost_usd"),
        )
        if isinstance(agent_result.get(field), (int, float))
        and not isinstance(agent_result.get(field), bool)
    }
    return usage or None


def _load_job(path: Path) -> dict[str, Any]:
    job = _load_json_object(path, "terminal-bench job artifact")
    for key in ("schema", "dataset", "tasks", "agent", "vessel"):
        if key not in job:
            raise ConfigError(f"terminal-bench job artifact is missing {key}")
    return job


def _load_roster_ids(path: Path) -> list[str]:
    if not path.exists():
        raise ConfigError(f"task roster file not found: {path}")
    roster_ids = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ConfigError(
                f"task roster line {line_number} is not valid JSON: {error}"
            ) from error
        instance_id = record.get("instance_id") if isinstance(record, dict) else None
        if not isinstance(instance_id, str) or not instance_id:
            raise ConfigError(
                f"task roster line {line_number}.instance_id must be non-empty"
            )
        roster_ids.append(instance_id)
    if not roster_ids:
        raise ConfigError("task roster must contain at least one record")
    return roster_ids


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_command(argv: list[str], cwd: Path) -> int:
    cwd.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(argv, cwd=cwd)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
