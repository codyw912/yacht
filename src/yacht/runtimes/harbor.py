"""Harbor runtime backend resolution (ADR 0012).

A harbor runtime never executes the vessel's harness itself: YACHT runs
the pinned launcher image, which runs Harbor, which runs task containers
with the vessel's agent installed inside. Resolution therefore carries
metadata and evidence paths only — rigging is applied in-container by
the yacht agent classes, never on the host.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from yacht.domain.model import Regatta, RiggingRecipe, RuntimeRecipe, Vessel
from yacht.runtimes import secrets as runtime_secrets


class HarborRuntimeResolutionError(ValueError):
    """Raised when a harbor runtime cannot be resolved safely."""


@dataclass(frozen=True)
class HarborRuntimeResolution:
    runtime: RuntimeRecipe
    riggings: tuple[RiggingRecipe, ...]
    instance_root: Path
    temp_home: Path
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
        secret_values: Mapping[str, str],
    ) -> dict[str, str]:
        env = dict(self.env)
        for secret_name in self.required_secret_names:
            if secret_name not in secret_values:
                raise HarborRuntimeResolutionError(
                    f"missing value for required secret {secret_name}; "
                    f"supply it at run time with "
                    f"--secret {secret_name}=@env:<VAR> or "
                    f"--secret {secret_name}=<value>"
                )
            secret = regatta.secrets[secret_name]
            if secret.source != "env" or secret.name is None:
                raise HarborRuntimeResolutionError(
                    f"harbor runtimes support env-source secrets only; "
                    f"secret {secret_name} uses source {secret.source}"
                )
            env[secret.name] = secret_values[secret_name]
        return env

    def secret_refs(self, regatta: Regatta) -> tuple[dict[str, object], ...]:
        refs = []
        for name in self.required_secret_names:
            secret = regatta.secrets[name]
            ref = secret.name if secret.name is not None else secret.source
            refs.append(
                {
                    "name": name,
                    "source": secret.source,
                    "ref": ref,
                    "redacted": True,
                }
            )
        return tuple(refs)


def resolve_harbor_runtime(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance_root: Path,
    workspace_path: Path,
) -> HarborRuntimeResolution:
    runtime = _runtime_for_vessel(regatta, vessel)
    if runtime.image is None:
        raise HarborRuntimeResolutionError(
            f"harbor runtime {runtime.name} must declare the launcher image"
        )
    if runtime.harness is None:
        raise HarborRuntimeResolutionError(
            f"harbor runtime {runtime.name} must declare a harness"
        )
    if runtime.harness_version is None:
        raise HarborRuntimeResolutionError(
            f"harbor runtime {runtime.name} must pin harness_version"
        )
    riggings = tuple(
        regatta.rigging_recipes[name]
        for name in vessel.rigging
        if name in regatta.rigging_recipes
    )
    env = dict(runtime.env)
    for rigging in riggings:
        env.update(rigging.env)
    return HarborRuntimeResolution(
        runtime=runtime,
        riggings=riggings,
        instance_root=instance_root,
        temp_home=instance_root / "home",
        workspace_path=workspace_path,
        env=env,
        command_prefix=("docker", "run", "--rm", runtime.image),
        command=("harbor", "run"),
        required_secret_names=runtime_secrets.required_secret_names(runtime, riggings),
        cleanup_paths=(instance_root,),
    )


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise HarborRuntimeResolutionError(
            f"vessel {vessel.name} does not define a runtime"
        )
    runtime = regatta.runtime_recipes.get(vessel.runtime)
    if runtime is None:
        raise HarborRuntimeResolutionError(
            f"vessel {vessel.name} references undefined runtime {vessel.runtime}"
        )
    return runtime
