from __future__ import annotations

from dataclasses import dataclass
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
from yacht.runtime_backend import RuntimePreparationError, runtime_backend_for_recipe
from yacht.schemas import (
    PREFLIGHT_SUMMARY_SCHEMA,
    validate_preflight_summary_document,
)

AgentPromptRunnerFactory = Callable[[RuntimeInstance, Path], AgentPromptRunner]
AGENT_PREFLIGHT_ADAPTERS = {"none", "pi", "local-smoke"}


@dataclass(frozen=True)
class PlannedPreflightCheck:
    name: str
    kind: str
    origin: str
    origin_name: str
    required: bool
    included: bool
    artifact_path: Path | None
    omitted_reason: str | None = None
    command: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    prompt: str | None = None
    expect_tool_calls: tuple[str, ...] = ()
    transcript_dir: Path | None = None

    def to_execution_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "origin": self.origin,
            "origin_name": self.origin_name,
            "required": self.required,
            "included": self.included,
            "artifact_path": (
                str(self.artifact_path) if self.artifact_path is not None else None
            ),
        }
        if self.omitted_reason is not None:
            payload["omitted_reason"] = self.omitted_reason
        if self.command:
            payload["command"] = list(self.command)
        if self.env:
            payload["env"] = list(self.env)
        if self.prompt is not None:
            payload["prompt"] = self.prompt
        if self.expect_tool_calls:
            payload["expect_tool_calls"] = list(self.expect_tool_calls)
        if self.transcript_dir is not None:
            payload["transcript_dir"] = str(self.transcript_dir)
        return payload

    def to_summary_json(self, status: str) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "kind": self.kind,
            "origin": self.origin,
            "origin_name": self.origin_name,
            "required": self.required,
            "included": self.included,
            "status": status,
        }
        if self.omitted_reason is not None:
            payload["omitted_reason"] = self.omitted_reason
        return payload


@dataclass(frozen=True)
class PlannedVesselPreflight:
    vessel: Vessel
    runtime: RuntimeRecipe
    checks: tuple[PlannedPreflightCheck, ...]
    workspace_path: Path
    trial_root: Path
    artifact_path: Path
    transcript_dir: Path

    def to_execution_json(self) -> dict[str, Any]:
        return {
            "name": self.vessel.name,
            "runtime": self.runtime.name,
            "workspace_path": str(self.workspace_path),
            "trial_root": str(self.trial_root),
            "artifact_path": str(self.artifact_path),
            "preflight_checks": [check.to_execution_json() for check in self.checks],
        }


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
    summary = {
        "schema": PREFLIGHT_SUMMARY_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "status": status,
        "preflight_failure_policy": regatta.preflight.failure_policy,
        "comparisons": comparison_results,
    }
    validate_preflight_summary_document(summary)
    return summary


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
    plan = _planned_vessel_preflight(
        regatta=regatta,
        comparison=comparison,
        vessel=vessel,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        include_agent_checks=include_agent_checks,
    )
    return plan.to_execution_json()


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(f"vessel {vessel.name} does not define a runtime")
    return regatta.runtime_recipes[vessel.runtime]


def _planned_vessel_preflight(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    logbook_dir: Path,
    workspace_path: Path,
    include_agent_checks: bool,
) -> PlannedVesselPreflight:
    runtime = _runtime_for_vessel(regatta, vessel)
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    artifact_path = logbook_dir / "preflight" / comparison.name / f"{vessel.name}.json"
    transcript_dir = logbook_dir / "transcripts" / comparison.name / vessel.name
    checks = _planned_preflight_checks(
        runtime=runtime,
        riggings=riggings,
        artifact_path=artifact_path,
        transcript_dir=transcript_dir,
        include_agent_checks=include_agent_checks,
    )
    return PlannedVesselPreflight(
        vessel=vessel,
        runtime=runtime,
        checks=tuple(checks),
        workspace_path=workspace_path,
        trial_root=logbook_dir / "runtime" / comparison.name / vessel.name,
        artifact_path=artifact_path,
        transcript_dir=transcript_dir,
    )


def _planned_preflight_checks(
    *,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> list[PlannedPreflightCheck]:
    checks = _planned_checks_from_recipe(
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
            _planned_checks_from_recipe(
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


def _planned_checks_from_recipe(
    *,
    origin: str,
    origin_name: str,
    recipe_required: bool,
    checks: tuple[PreflightCheck, ...],
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> list[PlannedPreflightCheck]:
    return [
        _planned_check(
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


def _planned_check(
    *,
    origin: str,
    origin_name: str,
    recipe_required: bool,
    check: PreflightCheck,
    artifact_path: Path,
    transcript_dir: Path,
    include_agent_checks: bool,
) -> PlannedPreflightCheck:
    included, omitted_reason = _check_inclusion(check.kind, include_agent_checks)
    return PlannedPreflightCheck(
        name=check.name,
        kind=check.kind,
        origin=origin,
        origin_name=origin_name,
        required=recipe_required and check.required,
        included=included,
        artifact_path=artifact_path if included else None,
        omitted_reason=omitted_reason,
        command=check.command,
        env=check.env,
        prompt=check.prompt,
        expect_tool_calls=check.expect_tool_calls,
        transcript_dir=(
            transcript_dir if check.kind in AGENT_CHECK_KINDS and included else None
        ),
    )


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
        include_agent_checks = agent_prompt_runner_factory is not None
        plan = _planned_vessel_preflight(
            regatta=regatta,
            comparison=comparison,
            vessel=vessel,
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            include_agent_checks=include_agent_checks,
        )
        instance = runtime_backend_for_recipe(plan.runtime).prepare(
            regatta=regatta,
            vessel=vessel,
            trial_root=logbook_dir / "runtime" / comparison.name,
            workspace_path=workspace_path,
            secret_values=secret_values,
        )
        if agent_prompt_runner_factory is None:
            artifact = execute_machine_preflight(
                regatta=regatta,
                vessel=vessel,
                instance=instance,
                artifact_path=plan.artifact_path,
                comparison=comparison,
            )
        else:
            artifact = execute_preflight(
                regatta=regatta,
                vessel=vessel,
                instance=instance,
                artifact_path=plan.artifact_path,
                comparison=comparison,
                agent_prompt_runner=agent_prompt_runner_factory(
                    instance,
                    plan.transcript_dir,
                ),
            )
        status = str(artifact["status"])
    except RuntimePreparationError as error:
        raise ConfigError(str(error)) from error
    return {
        "name": vessel.name,
        "status": status,
        "evidence_artifact_path": str(plan.artifact_path),
        "checks": _summary_checks(
            checks=plan.checks,
            artifact=artifact,
        ),
    }


def _summary_checks(
    *,
    checks: tuple[PlannedPreflightCheck, ...],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    status_by_name = {
        str(check["name"]): str(check["status"])
        for check in artifact["checks"]
    }
    return [_summary_check(check, status_by_name) for check in checks]


def _summary_check(
    check: PlannedPreflightCheck,
    status_by_name: dict[str, str],
) -> dict[str, Any]:
    status = status_by_name.get(check.name, "omitted")
    return check.to_summary_json(status)


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
