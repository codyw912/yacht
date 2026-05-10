from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from yacht.preflight import (
    AGENT_CHECK_KINDS,
    AgentPromptRunner,
    MACHINE_CHECK_KINDS,
    execute_machine_preflight,
    execute_preflight,
)
from yacht.regatta import (
    Comparison,
    ConfigError,
    PreflightCheck,
    Regatta,
    RiggingRecipe,
    RuntimeInstance,
    RuntimeRecipe,
    Vessel,
    load_regatta,
)
from yacht.runtime_backend import HostNixRuntimeBackend, RuntimePreparationError

AgentPromptRunnerFactory = Callable[[RuntimeInstance, Path], AgentPromptRunner]
AGENT_PREFLIGHT_ADAPTERS = {"none", "pi"}


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


def build_preflight_execution_plan(
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    agent_preflight: str,
) -> dict[str, Any]:
    if agent_preflight not in AGENT_PREFLIGHT_ADAPTERS:
        raise ConfigError(f"unsupported agent preflight adapter {agent_preflight}")

    regatta = load_regatta(config_path)
    if not regatta.comparisons:
        raise ConfigError("preflight requires at least one comparison")

    include_agent_checks = agent_preflight != "none"
    return {
        "regatta": regatta.name,
        "course": regatta.course.name,
        "mode": "dry-run",
        "preflight_failure_policy": regatta.preflight.failure_policy,
        "agent_preflight": agent_preflight,
        "comparisons": [
            _comparison_execution_plan(
                regatta=regatta,
                comparison=comparison,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                include_agent_checks=include_agent_checks,
            )
            for comparison in regatta.comparisons
        ],
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


def _comparison_execution_plan(
    *,
    regatta: Regatta,
    comparison: Comparison,
    logbook_dir: Path,
    workspace_path: Path,
    include_agent_checks: bool,
) -> dict[str, Any]:
    return {
        "name": comparison.name,
        "course": comparison.course,
        "preflight_failure_policy": regatta.preflight.failure_policy,
        "vessels": [
            _vessel_execution_plan(
                regatta=regatta,
                comparison=comparison,
                vessel=_vessel_by_name(regatta, vessel_name),
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                include_agent_checks=include_agent_checks,
            )
            for vessel_name in comparison.vessels
        ],
    }


def _vessel_execution_plan(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    logbook_dir: Path,
    workspace_path: Path,
    include_agent_checks: bool,
) -> dict[str, Any]:
    runtime = _runtime_for_vessel(regatta, vessel)
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    artifact_path = logbook_dir / "preflight" / comparison.name / f"{vessel.name}.json"
    transcript_dir = logbook_dir / "transcripts" / comparison.name / vessel.name
    return {
        "name": vessel.name,
        "runtime": runtime.name,
        "workspace_path": str(workspace_path),
        "trial_root": str(logbook_dir / "runtime" / comparison.name / vessel.name),
        "artifact_path": str(artifact_path),
        "preflight_checks": _preflight_check_execution_plan(
            runtime=runtime,
            riggings=riggings,
            artifact_path=artifact_path,
            transcript_dir=transcript_dir,
            include_agent_checks=include_agent_checks,
        ),
    }


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(f"vessel {vessel.name} does not define a runtime")
    return regatta.runtime_recipes[vessel.runtime]


def _preflight_check_execution_plan(
    *,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> list[dict[str, Any]]:
    checks = _checks_from_recipe(
        origin="runtime",
        origin_name=runtime.name,
        recipe_required=runtime.preflight.required,
        checks=runtime.preflight.checks,
        artifact_path=artifact_path,
        transcript_dir=transcript_dir,
        include_agent_checks=include_agent_checks,
    )
    for rigging in riggings:
        checks.extend(
            _checks_from_recipe(
                origin="rigging",
                origin_name=rigging.name,
                recipe_required=rigging.preflight.required,
                checks=rigging.preflight.checks,
                artifact_path=artifact_path,
                transcript_dir=transcript_dir,
                include_agent_checks=include_agent_checks,
            )
        )
    return checks


def _checks_from_recipe(
    *,
    origin: str,
    origin_name: str,
    recipe_required: bool,
    checks: tuple[PreflightCheck, ...],
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> list[dict[str, Any]]:
    return [
        _check_execution_plan(
            origin=origin,
            origin_name=origin_name,
            recipe_required=recipe_required,
            check=check,
            artifact_path=artifact_path,
            transcript_dir=transcript_dir,
            include_agent_checks=include_agent_checks,
        )
        for check in checks
    ]


def _check_execution_plan(
    *,
    origin: str,
    origin_name: str,
    recipe_required: bool,
    check: PreflightCheck,
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> dict[str, Any]:
    included, omitted_reason = _check_inclusion(check.kind, include_agent_checks)
    payload: dict[str, Any] = {
        "name": check.name,
        "kind": check.kind,
        "origin": origin,
        "origin_name": origin_name,
        "required": recipe_required and check.required,
        "included": included,
        "artifact_path": str(artifact_path) if included else None,
    }
    if omitted_reason is not None:
        payload["omitted_reason"] = omitted_reason
    if check.command:
        payload["command"] = list(check.command)
    if check.env:
        payload["env"] = list(check.env)
    if check.prompt is not None:
        payload["prompt"] = check.prompt
    if check.expect_tool_calls:
        payload["expect_tool_calls"] = list(check.expect_tool_calls)
    if check.kind in AGENT_CHECK_KINDS and included:
        payload["transcript_dir"] = str(transcript_dir)
    return payload


def _check_inclusion(kind: str, include_agent_checks: bool) -> tuple[bool, str | None]:
    if kind in MACHINE_CHECK_KINDS:
        return True, None
    if kind in AGENT_CHECK_KINDS:
        if include_agent_checks:
            return True, None
        return False, "agent preflight disabled"
    return False, f"unsupported preflight check kind {kind}"


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
) -> dict[str, Any]:
    try:
        runtime = _runtime_for_vessel(regatta, vessel)
        riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
        include_agent_checks = agent_prompt_runner_factory is not None
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
    return {
        "name": vessel.name,
        "status": status,
        "checks": _summary_checks(
            runtime=runtime,
            riggings=riggings,
            artifact=artifact,
            artifact_path=artifact_path,
            transcript_dir=logbook_dir / "transcripts" / comparison.name / vessel.name,
            include_agent_checks=include_agent_checks,
        ),
    }


def _summary_checks(
    *,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    artifact: dict[str, Any],
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> list[dict[str, Any]]:
    status_by_name = {
        str(check["name"]): str(check["status"])
        for check in artifact["checks"]
    }
    checks = _preflight_check_execution_plan(
        runtime=runtime,
        riggings=riggings,
        artifact_path=artifact_path,
        transcript_dir=transcript_dir,
        include_agent_checks=include_agent_checks,
    )
    return [_summary_check(check, status_by_name) for check in checks]


def _summary_check(
    check: dict[str, Any],
    status_by_name: dict[str, str],
) -> dict[str, Any]:
    status = status_by_name.get(str(check["name"]), "omitted")
    payload = {
        "name": check["name"],
        "kind": check["kind"],
        "required": check["required"],
        "included": check["included"],
        "status": status,
    }
    if "omitted_reason" in check:
        payload["omitted_reason"] = check["omitted_reason"]
    return payload


def _comparison_status(
    failure_policy: str,
    vessel_results: list[dict[str, Any]],
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
