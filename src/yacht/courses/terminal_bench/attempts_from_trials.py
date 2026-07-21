from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from yacht import __version__
from yacht.config.loader import load_regatta
from yacht.contracts.schemas import TASK_ATTEMPT_SCHEMA, validate_task_attempt_document
from yacht.courses.terminal_bench.harness import HARBOR_JOB_NAME
from yacht.domain.model import (
    Comparison,
    ConfigError,
    Regatta,
    RuntimeRecipe,
    SecretReference,
    Task,
    Vessel,
)
from yacht.logbook.paths import task_attempt_path
from yacht.workflows.benchmark_launcher_handoff import (
    native_report_path_from_launcher_handoff,
)
from yacht.workflows.provenance import tool_provenance


MACHINE_EVIDENCE_FORMAT = "terminal-bench-harbor-trial"
NATIVE_ROLLOUT_PROMPT = (
    "Task instruction delivered natively by the Harbor harness inside the "
    "task environment."
)


def write_terminal_bench_attempts_from_trials(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    vessel = _vessel(regatta, vessel_name)
    comparison = _comparison(regatta, vessel_name, comparison_name)
    runtime = _runtime(regatta, vessel)

    native_report_path = native_report_path_from_launcher_handoff(
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
    )
    report = _load_native_report(native_report_path)
    trials_by_task = _trials_by_task(report)

    artifact_paths = []
    completed = 0
    for task in regatta.course.tasks:
        trial = trials_by_task.get(task.id)
        artifact = _attempt_from_trial(
            regatta=regatta,
            comparison=comparison,
            vessel=vessel,
            runtime=runtime,
            task=task,
            trial=trial,
            native_report_path=native_report_path,
        )
        validate_task_attempt_document(artifact)
        artifact_path = task_attempt_path(logbook_dir, comparison, vessel, task)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact_paths.append(str(artifact_path))
        if artifact["status"] == "completed":
            completed += 1

    return {
        "status": "completed",
        "mode": "native-rollout",
        "vessel": vessel_name,
        "comparison": comparison.name,
        "attempt_count": len(artifact_paths),
        "completed_attempts": completed,
        "failed_attempts": len(artifact_paths) - completed,
        "artifact_paths": artifact_paths,
    }


def _attempt_from_trial(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    runtime: RuntimeRecipe,
    task: Task,
    trial: dict[str, Any] | None,
    native_report_path: Path,
) -> dict[str, Any]:
    completed = (
        trial is not None
        and trial.get("exception") is None
        and trial.get("reward") is not None
    )
    trial_dir = _trial_dir(trial, native_report_path)
    return {
        "schema": TASK_ATTEMPT_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "comparison": comparison.name,
        "vessel": vessel.name,
        "model": vessel.model,
        "rigging": list(vessel.rigging),
        "runtime": runtime.name,
        "status": "completed" if completed else "failed",
        "task": _task_to_json(task),
        "provenance": _provenance(regatta, vessel, runtime, trial),
        "runtime_context": {
            "backend": runtime.backend,
            "harness": runtime.harness,
            "agent": runtime.harness,
            "temp_home": trial_dir,
            "workspace_path": trial_dir,
            "command_prefix": [],
            "command": ["harbor", "run"],
            "cleanup_paths": [],
        },
        "prompt": NATIVE_ROLLOUT_PROMPT,
        "agent": _agent_to_json(trial, trial_dir, completed),
        "metrics": _metrics(trial),
        "secret_refs": _secret_refs(regatta, vessel, runtime),
    }


def _provenance(
    regatta: Regatta,
    vessel: Vessel,
    runtime: RuntimeRecipe,
    trial: dict[str, Any] | None,
) -> dict[str, Any]:
    agent = trial.get("agent") if isinstance(trial, dict) else None
    agent = agent if isinstance(agent, dict) else {}
    return {
        "yacht": {"version": __version__},
        "harness": {
            "name": runtime.harness,
            "version": _non_empty(agent.get("version")),
        },
        "model": {
            "configured": vessel.model,
            "resolved": _non_empty(agent.get("model")),
        },
        "runtime": {
            "backend": runtime.backend,
            "image": runtime.image,
        },
        "tools": tool_provenance(regatta, vessel),
    }


def _agent_to_json(
    trial: dict[str, Any] | None,
    trial_dir: str,
    completed: bool,
) -> dict[str, Any]:
    return {
        "exit_code": 0 if completed else 1,
        "response": "",
        "tool_calls": [],
        "transcript_path": trial_dir,
        "machine_evidence": _machine_evidence(trial),
    }


def _machine_evidence(trial: dict[str, Any] | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {"format": MACHINE_EVIDENCE_FORMAT}
    if trial is None:
        evidence["status"] = "trial-missing"
        return evidence
    for key in ("trial_name", "trial_dir", "started_at", "finished_at"):
        value = trial.get(key)
        if isinstance(value, str) and value:
            evidence[key] = value
    reward = trial.get("reward")
    if isinstance(reward, (int, float)) and not isinstance(reward, bool):
        evidence["reward"] = float(reward)
    agent = trial.get("agent")
    if isinstance(agent, dict):
        model = _non_empty(agent.get("model"))
        if model is not None:
            evidence["model"] = model
        harness_version = _non_empty(agent.get("version"))
        if harness_version is not None:
            evidence["harness_version"] = harness_version
    usage = trial.get("usage")
    if isinstance(usage, dict):
        numeric_usage = {
            key: value
            for key, value in usage.items()
            if key != "cost_usd"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0
        }
        if numeric_usage:
            evidence["usage"] = numeric_usage
        cost = usage.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            evidence["cost"] = {"total": cost}
    exception = trial.get("exception")
    if isinstance(exception, dict):
        evidence["exception"] = {
            "type": str(exception.get("type")),
            "message": str(exception.get("message")),
        }
    return evidence


def _metrics(trial: dict[str, Any] | None) -> dict[str, Any]:
    tokens = 0
    duration = 0.0
    if trial is not None:
        usage = trial.get("usage")
        if isinstance(usage, dict):
            for key in ("input_tokens", "output_tokens"):
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    tokens += max(value, 0)
        duration = _duration_seconds(trial)
    return {"tokens": tokens, "duration_seconds": duration}


def _duration_seconds(trial: dict[str, Any]) -> float:
    started = _parse_timestamp(trial.get("started_at"))
    finished = _parse_timestamp(trial.get("finished_at"))
    if started is None or finished is None:
        return 0.0
    seconds = (finished - started).total_seconds()
    return seconds if seconds >= 0 else 0.0


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _trials_by_task(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    trials = report.get("trials")
    if not isinstance(trials, list):
        raise ConfigError(
            "terminal-bench native report does not include trial summaries"
        )
    by_task: dict[str, dict[str, Any]] = {}
    for trial in trials:
        if not isinstance(trial, dict):
            raise ConfigError("terminal-bench trial summary must be a JSON object")
        task_name = trial.get("task_name")
        if not isinstance(task_name, str) or not task_name:
            raise ConfigError("terminal-bench trial summary is missing task_name")
        by_task[task_name] = trial
    return by_task


def _trial_dir(trial: dict[str, Any] | None, native_report_path: Path) -> str:
    if trial is not None:
        trial_dir = trial.get("trial_dir")
        if isinstance(trial_dir, str) and trial_dir:
            return trial_dir
    return str(native_report_path.parent.parent / "harbor-trials" / HARBOR_JOB_NAME)


def _load_native_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"native report not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"native report is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError("native report must be a JSON object")
    return payload


def _vessel(regatta: Regatta, vessel_name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == vessel_name:
            return vessel
    raise ConfigError(f"vessel {vessel_name} is not defined in the regatta config")


def _comparison(
    regatta: Regatta,
    vessel_name: str,
    comparison_name: str | None,
) -> Comparison:
    matches = [
        comparison
        for comparison in regatta.comparisons
        if vessel_name in comparison.vessels
        and (comparison_name is None or comparison.name == comparison_name)
    ]
    if not matches:
        raise ConfigError(f"vessel {vessel_name} is not part of a matching comparison")
    if len(matches) > 1:
        raise ConfigError(
            f"vessel {vessel_name} is in multiple comparisons; pass --comparison"
        )
    return matches[0]


def _runtime(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(
            f"vessel {vessel.name} must declare a runtime for terminal-bench"
        )
    runtime = regatta.runtime_recipes.get(vessel.runtime)
    if runtime is None:
        raise ConfigError(
            f"vessel {vessel.name} references undefined runtime {vessel.runtime}"
        )
    return runtime


def _task_to_json(task: Task) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": task.id,
        "title": task.title,
        "difficulty": task.difficulty,
    }
    if task.problem_statement is not None:
        payload["problem_statement"] = task.problem_statement
    return payload


def _secret_refs(
    regatta: Regatta,
    vessel: Vessel,
    runtime: RuntimeRecipe,
) -> list[dict[str, Any]]:
    names = list(runtime.required_secrets)
    for rigging_name in vessel.rigging:
        rigging = regatta.rigging_recipes.get(rigging_name)
        if rigging is not None:
            names.extend(rigging.required_secrets)
    return [_secret_ref(name, regatta.secrets[name]) for name in dict.fromkeys(names)]


def _secret_ref(name: str, secret: SecretReference) -> dict[str, Any]:
    if secret.source == "env" and secret.name is not None:
        ref = secret.name
    elif secret.source == "file" and secret.path is not None:
        ref = secret.path
    else:
        ref = secret.source
    return {"name": name, "source": secret.source, "ref": ref, "redacted": True}


def _non_empty(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
