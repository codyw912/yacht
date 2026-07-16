from __future__ import annotations

from pathlib import Path
from typing import Protocol

from yacht.runtimes.container import ContainerRuntimeResolution
from yacht.runtimes.container import ContainerRuntimeResolutionError
from yacht.runtimes.container import resolve_container_runtime
from yacht.runtimes.host_nix import HostNixRuntimeResolution
from yacht.runtimes.host_nix import HostNixRuntimeResolutionError
from yacht.runtimes.host_nix import resolve_host_nix_runtime
from yacht.domain.model import (
    ConfigError,
    Regatta,
    RuntimeInstance,
    RuntimeRecipe,
    RuntimeSetupResult,
    Vessel,
)
from yacht.runtimes.rigging_setup import (
    RiggingSetupError,
    SetupCommandRunner,
    SetupProcessResult as SetupProcessResult,
    apply_rigging_setup,
    plan_rigging_setup,
    run_setup_command,
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
    ) -> RuntimeInstance: ...


def runtime_backend_for_recipe(runtime: RuntimeRecipe) -> RuntimeBackend:
    if runtime.backend == "host-nix":
        return HostNixRuntimeBackend()
    if runtime.backend == "container":
        return ContainerRuntimeBackend()
    raise ConfigError(f"unsupported runtime backend {runtime.backend}")


class HostNixRuntimeBackend:
    def __init__(self, setup_runner: SetupCommandRunner | None = None) -> None:
        self._setup_runner = setup_runner or run_setup_command

    def prepare(
        self,
        *,
        regatta: Regatta,
        vessel: Vessel,
        trial_root: Path,
        workspace_path: Path,
        secret_values: dict[str, str],
    ) -> RuntimeInstance:
        try:
            resolution = resolve_host_nix_runtime(
                regatta=regatta,
                vessel=vessel,
                instance_root=trial_root / vessel.name,
                workspace_path=workspace_path,
            )
            env = resolution.env_with_secret_values(
                regatta=regatta,
                secret_values=secret_values,
            )
        except HostNixRuntimeResolutionError as error:
            raise RuntimePreparationError(str(error)) from error

        _create_runtime_dirs(resolution.temp_home)
        setup_results = _apply_rigging_installs(
            resolution=resolution,
            env=env,
            setup_runner=self._setup_runner,
        )

        return RuntimeInstance(
            runtime=resolution.runtime,
            temp_home=resolution.temp_home,
            workspace_path=resolution.workspace_path,
            env=env,
            command_prefix=resolution.command_prefix,
            cleanup_paths=resolution.cleanup_paths,
            setup_results=setup_results,
        )


class ContainerRuntimeBackend:
    def __init__(self, setup_runner: SetupCommandRunner | None = None) -> None:
        self._setup_runner = setup_runner or run_setup_command

    def prepare(
        self,
        *,
        regatta: Regatta,
        vessel: Vessel,
        trial_root: Path,
        workspace_path: Path,
        secret_values: dict[str, str],
    ) -> RuntimeInstance:
        try:
            resolution = resolve_container_runtime(
                regatta=regatta,
                vessel=vessel,
                instance_root=trial_root / vessel.name,
                workspace_path=workspace_path,
            )
            env = resolution.env_with_secret_values(
                regatta=regatta,
                secret_values=secret_values,
            )
        except ContainerRuntimeResolutionError as error:
            raise RuntimePreparationError(str(error)) from error

        _create_runtime_dirs(resolution.temp_home)
        setup_results = _apply_rigging_installs(
            resolution=resolution,
            env=env,
            setup_runner=self._setup_runner,
        )

        return RuntimeInstance(
            runtime=resolution.runtime,
            temp_home=resolution.temp_home,
            workspace_path=resolution.workspace_path,
            env=env,
            command_prefix=resolution.command_prefix,
            cleanup_paths=resolution.cleanup_paths,
            setup_results=setup_results,
        )


def _create_runtime_dirs(temp_home: Path) -> None:
    for path in (
        temp_home,
        temp_home / ".config",
        temp_home / ".cache",
        temp_home / ".cache" / "npm",
        temp_home / ".local" / "state",
        temp_home / ".local" / "state" / "npm-global",
        temp_home / ".local" / "state" / "npm-global" / "bin",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _apply_rigging_installs(
    *,
    resolution: HostNixRuntimeResolution | ContainerRuntimeResolution,
    env: dict[str, str],
    setup_runner: SetupCommandRunner,
) -> tuple[RuntimeSetupResult, ...]:
    try:
        plan = plan_rigging_setup(
            runtime=resolution.runtime,
            riggings=resolution.riggings,
            command_prefix=resolution.command_prefix,
        )
        return apply_rigging_setup(
            plan=plan,
            env=env,
            workspace_path=resolution.workspace_path,
            setup_runner=setup_runner,
            temp_home=resolution.temp_home,
        )
    except RiggingSetupError as error:
        raise RuntimePreparationError(str(error)) from error
