from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.regatta import (
    Comparison,
    ConfigError,
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    SecretReference,
    Vessel,
    load_regatta,
)


def build_runtime_instances_plan(
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    if not regatta.comparisons:
        raise ConfigError("runtime instances require at least one comparison")
    return {
        "regatta": regatta.name,
        "course": regatta.course.name,
        "mode": "dry-run",
        "workspace_path": str(workspace_path),
        "comparisons": [
            _comparison_to_json(
                regatta=regatta,
                comparison=comparison,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
            )
            for comparison in regatta.comparisons
        ],
    }


def _comparison_to_json(
    *,
    regatta: Regatta,
    comparison: Comparison,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    return {
        "name": comparison.name,
        "course": comparison.course,
        "vessels": [
            _vessel_to_json(
                regatta=regatta,
                comparison=comparison,
                vessel=_vessel_by_name(regatta, vessel_name),
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
            )
            for vessel_name in comparison.vessels
        ],
    }


def _vessel_to_json(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    runtime = _runtime_for_vessel(regatta, vessel)
    if runtime.backend != "host-nix":
        raise ConfigError(
            f"runtime {runtime.name} uses unsupported backend {runtime.backend}"
        )
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    trial_root = logbook_dir / "runtime" / comparison.name / vessel.name
    temp_home = trial_root / "home"
    trial_state = temp_home / ".local" / "state"
    return {
        "name": vessel.name,
        "runtime": runtime.name,
        "backend": runtime.backend,
        "trial_root": str(trial_root),
        "temp_home": str(temp_home),
        "workspace_path": str(workspace_path),
        "command_prefix": ["nix", "develop", runtime.flake, "--command"],
        "command": list(runtime.command),
        "env": _runtime_env(
            regatta=regatta,
            runtime=runtime,
            riggings=riggings,
            temp_home=temp_home,
            workspace_path=workspace_path,
            trial_state=trial_state,
        ),
        "secret_refs": [
            _secret_ref_to_json(name, regatta.secrets[name])
            for name in _required_secret_names(runtime, riggings)
        ],
        "cleanup_paths": [str(trial_root)],
    }


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(f"vessel {vessel.name} does not define a runtime")
    return regatta.runtime_recipes[vessel.runtime]


def _runtime_env(
    *,
    regatta: Regatta,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    temp_home: Path,
    workspace_path: Path,
    trial_state: Path,
) -> dict[str, str]:
    env = {
        "HOME": str(temp_home),
        "XDG_CONFIG_HOME": str(temp_home / ".config"),
        "XDG_CACHE_HOME": str(temp_home / ".cache"),
        "XDG_STATE_HOME": str(trial_state),
    }
    env.update(_expand_env_values(runtime.env, temp_home, workspace_path, trial_state))
    for rigging in riggings:
        env.update(
            _expand_env_values(rigging.env, temp_home, workspace_path, trial_state)
        )
    for secret_name in _required_secret_names(runtime, riggings):
        secret = regatta.secrets[secret_name]
        if secret.source == "env" and secret.name is not None:
            env[secret.name] = f"{{secret:{secret_name}}}"
    return env


def _expand_env_values(
    values: dict[str, str],
    temp_home: Path,
    workspace_path: Path,
    trial_state: Path,
) -> dict[str, str]:
    replacements = {
        "{trial_home}": str(temp_home),
        "{trial_state}": str(trial_state),
        "{workspace}": str(workspace_path),
    }
    return {
        key: _replace_placeholders(value, replacements)
        for key, value in values.items()
    }


def _replace_placeholders(value: str, replacements: dict[str, str]) -> str:
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, replacement)
    return value


def _required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


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


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison references undefined vessel {name}")
