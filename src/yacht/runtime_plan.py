from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.regatta import (
    Comparison,
    ConfigError,
    CourseAdapter,
    PreflightCheck,
    PreflightRecipe,
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    SecretReference,
    Vessel,
    load_regatta,
)


ISOLATED_ENV = {
    "HOME": "{trial_home}",
    "XDG_CONFIG_HOME": "{trial_home}/.config",
    "XDG_CACHE_HOME": "{trial_home}/.cache",
    "XDG_STATE_HOME": "{trial_home}/.local/state",
}


def build_runtime_plan(config_path: Path) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    plan: dict[str, Any] = {
        "regatta": regatta.name,
        "course": regatta.course.name,
    }
    if regatta.course.adapter is not None:
        plan["course_adapter"] = _course_adapter_to_json(
            regatta.course.adapter,
            task_ids=tuple(task.id for task in regatta.course.tasks),
        )
    plan["preflight_failure_policy"] = regatta.preflight.failure_policy
    plan["comparisons"] = [
        _comparison_to_json(regatta, comparison)
        for comparison in regatta.comparisons
    ]
    plan["vessels"] = [_vessel_to_json(regatta, vessel) for vessel in regatta.vessels]
    return plan


def _comparison_to_json(regatta: Regatta, comparison: Comparison) -> dict[str, Any]:
    return {
        "name": comparison.name,
        "course": comparison.course,
        "vessels": list(comparison.vessels),
        "preflight_failure_policy": regatta.preflight.failure_policy,
    }


def _vessel_to_json(regatta: Regatta, vessel: Vessel) -> dict[str, Any]:
    runtime = _runtime_for_vessel(regatta, vessel)
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    env = _merge_env(runtime, riggings)
    required_secrets = _required_secret_names(runtime, riggings)

    return {
        "name": vessel.name,
        "model": vessel.model,
        "rigging": list(vessel.rigging),
        "runtime": _runtime_to_json(runtime),
        "env": env,
        "secret_refs": [
            _secret_ref_to_json(name, regatta.secrets[name]) for name in required_secrets
        ],
        "preflight_checks": _preflight_checks_to_json(runtime, riggings),
    }


def _course_adapter_to_json(
    adapter: CourseAdapter,
    task_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "kind": adapter.kind,
        "dataset": adapter.dataset,
        "split": adapter.split,
        "harness": adapter.harness,
        "task_ids": list(task_ids),
        "grading": {
            "delegated_to": adapter.kind,
            "execution": f"{adapter.harness}-harness",
            "status": "planned",
        },
    }


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        vessel_index = regatta.vessels.index(vessel)
        raise ConfigError(f"vessels[{vessel_index}].runtime is required for planning")
    return regatta.runtime_recipes[vessel.runtime]


def _merge_env(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> dict[str, str]:
    env = dict(ISOLATED_ENV)
    env.update(runtime.env)
    for rigging in riggings:
        env.update(rigging.env)
    return env


def _required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


def _runtime_to_json(runtime: RuntimeRecipe) -> dict[str, Any]:
    return {
        "name": runtime.name,
        "backend": runtime.backend,
        "flake": runtime.flake,
        "command_prefix": _command_prefix(runtime),
        "command": list(runtime.command),
        "mounts": list(runtime.mounts),
    }


def _command_prefix(runtime: RuntimeRecipe) -> list[str]:
    if runtime.backend == "host-nix":
        return ["nix", "develop", runtime.flake, "--command"]
    return []


def _secret_ref_to_json(name: str, secret: SecretReference) -> dict[str, Any]:
    return {
        "name": name,
        "source": secret.source,
        "ref": _secret_ref_label(secret),
        "redacted": True,
    }


def _secret_ref_label(secret: SecretReference) -> str:
    if secret.source == "env" and secret.name is not None:
        return secret.name
    if secret.source == "file" and secret.path is not None:
        return secret.path
    raise ConfigError(f"secret reference source {secret.source} is not resolvable")


def _preflight_checks_to_json(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> list[dict[str, Any]]:
    checks = _checks_from_recipe("runtime", runtime.name, runtime.preflight)
    for rigging in riggings:
        checks.extend(_checks_from_recipe("rigging", rigging.name, rigging.preflight))
    return checks


def _checks_from_recipe(
    origin: str,
    origin_name: str,
    recipe: PreflightRecipe,
) -> list[dict[str, Any]]:
    return [
        _preflight_check_to_json(origin, origin_name, recipe.required, check)
        for check in recipe.checks
    ]


def _preflight_check_to_json(
    origin: str,
    origin_name: str,
    recipe_required: bool,
    check: PreflightCheck,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": check.name,
        "kind": check.kind,
        "origin": origin,
        "origin_name": origin_name,
        "required": recipe_required and check.required,
    }
    if check.command:
        payload["command"] = list(check.command)
    if check.env:
        payload["env"] = list(check.env)
    if check.prompt is not None:
        payload["prompt"] = check.prompt
    if check.expect_tool_calls:
        payload["expect_tool_calls"] = list(check.expect_tool_calls)
    return payload
