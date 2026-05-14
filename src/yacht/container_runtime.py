from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from yacht.regatta import (
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    SecretReference,
    Vessel,
)


class ContainerRuntimeResolutionError(ValueError):
    """Raised when a container runtime cannot be resolved safely."""


@dataclass(frozen=True)
class ContainerRuntimeResolution:
    runtime: RuntimeRecipe
    riggings: tuple[RiggingRecipe, ...]
    instance_root: Path
    temp_home: Path
    workspace_path: Path
    container_home: str
    container_workspace: str
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

    def secret_refs(self, regatta: Regatta) -> tuple[dict[str, object], ...]:
        return tuple(
            _secret_ref_to_json(name, regatta.secrets[name])
            for name in self.required_secret_names
        )


def resolve_container_runtime(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance_root: Path,
    workspace_path: Path,
) -> ContainerRuntimeResolution:
    runtime = _runtime_for_vessel(regatta, vessel)
    if runtime.backend != "container":
        raise ContainerRuntimeResolutionError(
            f"runtime {runtime.name} uses unsupported backend {runtime.backend}"
        )
    if runtime.image is None:
        raise ContainerRuntimeResolutionError(
            f"runtime {runtime.name} is missing image"
        )

    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    temp_home = instance_root / "home"
    container_home = runtime.container_home
    container_workspace = runtime.container_workspace
    return ContainerRuntimeResolution(
        runtime=runtime,
        riggings=riggings,
        instance_root=instance_root,
        temp_home=temp_home,
        workspace_path=workspace_path,
        container_home=container_home,
        container_workspace=container_workspace,
        env=_runtime_env(
            runtime=runtime,
            riggings=riggings,
            container_home=container_home,
            container_workspace=container_workspace,
        ),
        command_prefix=_command_prefix(
            runtime=runtime,
            temp_home=temp_home,
            workspace_path=workspace_path,
        ),
        command=tuple(runtime.command),
        required_secret_names=_required_secret_names(runtime, riggings),
        cleanup_paths=(instance_root,),
    )


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ContainerRuntimeResolutionError(
            f"vessel {vessel.name} does not define a runtime"
        )
    return regatta.runtime_recipes[vessel.runtime]


def _runtime_env(
    *,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    container_home: str,
    container_workspace: str,
) -> dict[str, str]:
    home = PurePosixPath(container_home)
    trial_state = home / ".local" / "state"
    env = {
        "HOME": str(home),
        "PATH": f"{trial_state / 'npm-global' / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "NPM_CONFIG_CACHE": str(home / ".cache" / "npm"),
        "NPM_CONFIG_PREFIX": str(trial_state / "npm-global"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(trial_state),
    }
    workspace = PurePosixPath(container_workspace)
    env.update(
        _expand_env_values(runtime.env, home, workspace, trial_state)
    )
    for rigging in riggings:
        env.update(
            _expand_env_values(
                rigging.env,
                home,
                workspace,
                trial_state,
            )
        )
    return env


def _expand_env_values(
    values: dict[str, str],
    container_home: PurePosixPath,
    container_workspace: PurePosixPath,
    trial_state: PurePosixPath,
) -> dict[str, str]:
    replacements = {
        "{trial_home}": str(container_home),
        "{trial_state}": str(trial_state),
        "{workspace}": str(container_workspace),
    }
    return {
        key: _replace_placeholders(value, replacements)
        for key, value in values.items()
    }


def _replace_placeholders(value: str, replacements: dict[str, str]) -> str:
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, replacement)
    return value


def _command_prefix(
    *,
    runtime: RuntimeRecipe,
    temp_home: Path | str,
    workspace_path: Path | str,
) -> tuple[str, ...]:
    if runtime.image is None:
        raise ContainerRuntimeResolutionError(
            f"runtime {runtime.name} is missing image"
        )
    return (
        "docker",
        "run",
        "--rm",
        "--workdir",
        runtime.container_workspace,
        "--mount",
        f"type=bind,source={workspace_path},target={runtime.container_workspace}",
        "--mount",
        f"type=bind,source={temp_home},target={runtime.container_home}",
        runtime.image,
    )


def container_command_prefix_template(runtime: RuntimeRecipe) -> list[str]:
    return list(
        _command_prefix(
            runtime=runtime,
            temp_home="{trial_home}",
            workspace_path="{workspace}",
        )
    )


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
    raise ContainerRuntimeResolutionError(
        f"secret reference source {secret.source} is not resolvable"
    )
