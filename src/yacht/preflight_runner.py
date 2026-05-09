from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from yacht.preflight import (
    AgentPromptRunner,
    execute_machine_preflight,
    execute_preflight,
)
from yacht.regatta import (
    Comparison,
    ConfigError,
    Regatta,
    RuntimeInstance,
    Vessel,
    load_regatta,
)
from yacht.runtime_backend import HostNixRuntimeBackend, RuntimePreparationError

AgentPromptRunnerFactory = Callable[[RuntimeInstance, Path], AgentPromptRunner]


def run_preflight(
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory | None = None,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    if not regatta.comparisons:
        raise ConfigError("preflight requires at least one comparison")

    comparison_results = [
        _run_comparison_preflight(
            regatta=regatta,
            comparison=comparison,
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent_prompt_runner_factory=agent_prompt_runner_factory,
        )
        for comparison in regatta.comparisons
    ]
    status = "invalid" if any(
        comparison["status"] == "invalid" for comparison in comparison_results
    ) else "passed"
    return {
        "regatta": regatta.name,
        "course": regatta.course.name,
        "status": status,
        "preflight_failure_policy": regatta.preflight.failure_policy,
        "comparisons": comparison_results,
    }


def parse_secret_values(values: list[str]) -> dict[str, str]:
    secrets = {}
    for value in values:
        if "=" not in value:
            raise ConfigError("secrets must use NAME=VALUE format")
        name, secret_value = value.split("=", maxsplit=1)
        if not name:
            raise ConfigError("secret names must be non-empty")
        secrets[name] = secret_value
    return secrets


def _run_comparison_preflight(
    *,
    regatta: Regatta,
    comparison: Comparison,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory | None,
) -> dict[str, Any]:
    vessel_results = [
        _run_vessel_preflight(
            regatta=regatta,
            comparison=comparison,
            vessel=_vessel_by_name(regatta, vessel_name),
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent_prompt_runner_factory=agent_prompt_runner_factory,
        )
        for vessel_name in comparison.vessels
    ]
    status = _comparison_status(regatta.preflight.failure_policy, vessel_results)
    return {
        "name": comparison.name,
        "status": status,
        "vessels": vessel_results,
    }


def _run_vessel_preflight(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory | None,
) -> dict[str, str]:
    try:
        instance = HostNixRuntimeBackend().prepare(
            regatta=regatta,
            vessel=vessel,
            trial_root=logbook_dir / "runtime" / comparison.name,
            workspace_path=workspace_path,
            secret_values=secret_values,
        )
        artifact_path = (
            logbook_dir / "preflight" / comparison.name / f"{vessel.name}.json"
        )
        if agent_prompt_runner_factory is None:
            artifact = execute_machine_preflight(
                regatta=regatta,
                vessel=vessel,
                instance=instance,
                artifact_path=artifact_path,
                comparison=comparison,
            )
        else:
            artifact = execute_preflight(
                regatta=regatta,
                vessel=vessel,
                instance=instance,
                artifact_path=artifact_path,
                comparison=comparison,
                agent_prompt_runner=agent_prompt_runner_factory(
                    instance,
                    logbook_dir / "transcripts" / comparison.name / vessel.name,
                ),
            )
        status = str(artifact["status"])
    except RuntimePreparationError as error:
        raise ConfigError(str(error)) from error
    return {"name": vessel.name, "status": status}


def _comparison_status(
    failure_policy: str,
    vessel_results: list[dict[str, str]],
) -> str:
    if any(vessel["status"] != "passed" for vessel in vessel_results):
        if failure_policy == "abort-group":
            return "invalid"
        return "failed"
    return "passed"


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison references undefined vessel {name}")
