from __future__ import annotations

from pathlib import Path
from typing import Protocol

from yacht.regatta import (
    Regatta,
    RiggingRecipe,
    RuntimeInstance,
    RuntimeRecipe,
    SecretReference,
    Vessel,
)


class RuntimePreparationError(ValueError):
    """Raised when a runtime instance cannot be prepared safely."""


class RuntimeBackend(Protocol):
    def prepare(
        self,
        *,
        regatta: Regatta,
        vessel: Vessel,
        trial_root: Path,
        workspace_path: Path,
        secret_values: dict[str, str],
    ) -> RuntimeInstance:
        ...


class HostNixRuntimeBackend:
    def prepare(
        self,
        *,
        regatta: Regatta,
        vessel: Vessel,
        trial_root: Path,
        workspace_path: Path,
        secret_values: dict[str, str],
    ) -> RuntimeInstance:
        runtime = _runtime_for_vessel(regatta, vessel)
        if runtime.backend != "host-nix":
            raise RuntimePreparationError(
                f"runtime {runtime.name} uses unsupported backend {runtime.backend}"
            )

        riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
        instance_root = trial_root / vessel.name
        temp_home = instance_root / "home"
        trial_state = temp_home / ".local" / "state"
        _create_runtime_dirs(temp_home)

        env = _runtime_env(
            runtime=runtime,
            riggings=riggings,
            temp_home=temp_home,
            workspace_path=workspace_path,
            trial_state=trial_state,
        )
        env.update(
            _secret_env(
                regatta=regatta,
                runtime=runtime,
                riggings=riggings,
                secret_values=secret_values,
            )
        )

        return RuntimeInstance(
            runtime=runtime,
            temp_home=temp_home,
            workspace_path=workspace_path,
            env=env,
            command_prefix=("nix", "develop", runtime.flake, "--command"),
            cleanup_paths=(instance_root,),
        )


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise RuntimePreparationError(f"vessel {vessel.name} does not define a runtime")
    return regatta.runtime_recipes[vessel.runtime]


def _create_runtime_dirs(temp_home: Path) -> None:
    for path in (
        temp_home,
        temp_home / ".config",
        temp_home / ".cache",
        temp_home / ".local" / "state",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _runtime_env(
    *,
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
    env.update(
        _expand_env_values(runtime.env, temp_home, workspace_path, trial_state)
    )
    for rigging in riggings:
        env.update(
            _expand_env_values(rigging.env, temp_home, workspace_path, trial_state)
        )
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


def _secret_env(
    *,
    regatta: Regatta,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    secret_values: dict[str, str],
) -> dict[str, str]:
    env = {}
    for secret_name in _required_secret_names(runtime, riggings):
        if secret_name not in secret_values:
            raise RuntimePreparationError(
                f"missing value for required secret {secret_name}"
            )
        secret = regatta.secrets[secret_name]
        env.update(_secret_to_env(secret_name, secret, secret_values[secret_name]))
    return env


def _required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


def _secret_to_env(
    secret_name: str,
    secret: SecretReference,
    value: str,
) -> dict[str, str]:
    if secret.source == "env" and secret.name is not None:
        return {secret.name: value}
    raise RuntimePreparationError(
        f"secret {secret_name} source {secret.source} cannot be injected as env"
    )
