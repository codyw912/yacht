from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yacht.regatta import (
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    SecretReference,
    Vessel,
)


class HostNixRuntimeResolutionError(ValueError):
    """Raised when a host Nix runtime cannot be resolved safely."""


@dataclass(frozen=True)
class HostNixRuntimeResolution:
    runtime: RuntimeRecipe
    riggings: tuple[RiggingRecipe, ...]
    instance_root: Path
    temp_home: Path
    trial_state: Path
    workspace_path: Path
    env: dict[str, str]
    command_prefix: tuple[str, ...]
    command: tuple[str, ...]
    required_secret_names: tuple[str, ...]
    cleanup_paths: tuple[Path, ...]

    def env_with_secret_placeholders(self, regatta: Regatta) -> dict[str, str]:
        env = dict(self.env)
        for secret_name in self.required_secret_names:
            secret = regatta.secrets[secret_name]
            if secret.source == "env" and secret.name is not None:
                env[secret.name] = f"{{secret:{secret_name}}}"
        return env

    def env_with_secret_values(
        self,
        regatta: Regatta,
        secret_values: dict[str, str],
    ) -> dict[str, str]:
        env = dict(self.env)
        for secret_name in self.required_secret_names:
            if secret_name not in secret_values:
                raise HostNixRuntimeResolutionError(
                    f"missing value for required secret {secret_name}"
                )
            secret = regatta.secrets[secret_name]
            env.update(_secret_to_env(secret_name, secret, secret_values[secret_name]))
        return env

    def secret_refs(self, regatta: Regatta) -> tuple[dict[str, object], ...]:
        return tuple(
            _secret_ref_to_json(name, regatta.secrets[name])
            for name in self.required_secret_names
        )


def resolve_host_nix_runtime(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance_root: Path,
    workspace_path: Path,
) -> HostNixRuntimeResolution:
    runtime = _runtime_for_vessel(regatta, vessel)
    if runtime.backend != "host-nix":
        raise HostNixRuntimeResolutionError(
            f"runtime {runtime.name} uses unsupported backend {runtime.backend}"
        )
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    temp_home = instance_root / "home"
    trial_state = temp_home / ".local" / "state"
    return HostNixRuntimeResolution(
        runtime=runtime,
        riggings=riggings,
        instance_root=instance_root,
        temp_home=temp_home,
        trial_state=trial_state,
        workspace_path=workspace_path,
        env=_runtime_env(
            runtime=runtime,
            riggings=riggings,
            temp_home=temp_home,
            workspace_path=workspace_path,
            trial_state=trial_state,
        ),
        command_prefix=("nix", "develop", runtime.flake, "--command"),
        command=tuple(runtime.command),
        required_secret_names=_required_secret_names(runtime, riggings),
        cleanup_paths=(instance_root,),
    )


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise HostNixRuntimeResolutionError(
            f"vessel {vessel.name} does not define a runtime"
        )
    return regatta.runtime_recipes[vessel.runtime]


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
    env.update(_expand_env_values(runtime.env, temp_home, workspace_path, trial_state))
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


def _required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


def _secret_ref_to_json(name: str, secret: SecretReference) -> dict[str, object]:
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
    raise HostNixRuntimeResolutionError(
        f"secret reference source {secret.source} is not resolvable"
    )


def _secret_to_env(
    secret_name: str,
    secret: SecretReference,
    value: str,
) -> dict[str, str]:
    if secret.source == "env" and secret.name is not None:
        return {secret.name: value}
    raise HostNixRuntimeResolutionError(
        f"secret {secret_name} source {secret.source} cannot be injected as env"
    )
