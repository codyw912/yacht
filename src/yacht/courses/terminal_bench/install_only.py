from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yacht.courses.terminal_bench.harness import (
    HARBOR_JOB_NAME,
    harbor_command,
    harbor_run_config,
)
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import ConfigError, Regatta


InstallOnlyCommandRunner = Callable[[tuple[str, ...], Path], Any]


def run_terminal_bench_install_only(
    *,
    regatta: Regatta,
    vessel_name: str,
    work_dir: Path,
    command_runner: InstallOnlyCommandRunner,
) -> dict[str, Any]:
    if not regatta.course.tasks:
        raise ConfigError("install-only preflight requires at least one course task")
    job = render_terminal_bench_job(regatta=regatta, vessel_name=vessel_name)
    job = {**job, "tasks": [job["tasks"][0]]}

    work_dir.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "harbor-run-config.json"
    config_path.write_text(
        json.dumps(
            harbor_run_config(job, trials_dir=work_dir), indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    tasks_path = Path(str(job["dataset"]["path"])) if "path" in job["dataset"] else None
    command = harbor_command(
        config_path,
        trials_dir=work_dir,
        secret_env=[str(name) for name in job.get("secret_env", [])],
        launcher_image=str(job["launcher_image"]),
        tasks_path=tasks_path,
    )
    command.append("--install-only")

    result = command_runner(tuple(command), work_dir)
    evidence: dict[str, Any] = {
        "task": str(job["tasks"][0]),
        "launcher_image": str(job["launcher_image"]),
        "argv": list(command),
        "exit_code": int(result.exit_code),
    }
    if result.exit_code != 0:
        evidence["stderr"] = str(result.stderr)[-2000:]
        return {"status": "failed", "evidence": evidence}

    trial = _first_trial_result(work_dir)
    if trial is None:
        evidence["error"] = "harbor run produced no trial result"
        return {"status": "failed", "evidence": evidence}

    evidence["trial_dir"] = trial["trial_dir"]
    agent_info = trial.get("agent_info")
    if isinstance(agent_info, dict):
        evidence["agent"] = {
            "name": agent_info.get("name"),
            "version": agent_info.get("version"),
        }
    exception_info = trial.get("exception_info")
    if isinstance(exception_info, dict):
        evidence["exception"] = {
            "type": str(exception_info.get("exception_type")),
            "message": str(exception_info.get("exception_message")),
        }
        return {"status": "failed", "evidence": evidence}

    installed_version = None
    if isinstance(agent_info, dict):
        version = agent_info.get("version")
        if isinstance(version, str) and version:
            installed_version = version
    if installed_version is None:
        evidence["error"] = "trial result does not record the installed agent version"
        return {"status": "failed", "evidence": evidence}

    return {"status": "passed", "evidence": evidence}


def _first_trial_result(work_dir: Path) -> dict[str, Any] | None:
    for result_path in sorted((work_dir / HARBOR_JOB_NAME).glob("*/result.json")):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["trial_dir"] = str(result_path.parent)
            return payload
    return None
