from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from yacht.runtimes.container import ContainerRuntimeResolution
from yacht.runtimes.container import ContainerRuntimeResolutionError
from yacht.runtimes.container import resolve_container_runtime
from yacht.runtimes.host_nix import HostNixRuntimeResolution
from yacht.runtimes.host_nix import HostNixRuntimeResolutionError
from yacht.runtimes.host_nix import resolve_host_nix_runtime
from yacht.domain.model import (
    ConfigError,
    Regatta,
    RiggingInstallStep,
    RuntimeInstance,
    RuntimeRecipe,
    RuntimeSetupResult,
    Vessel,
)
from yacht.runtimes.capabilities import unsupported_rigging_capability_reasons
from yacht.runtimes.process import subprocess_env


class RuntimePreparationError(ValueError):
    """Raised when a runtime instance cannot be prepared safely."""


@dataclass(frozen=True)
class SetupProcessResult:
    exit_code: int
    stdout: str
    stderr: str


SetupCommandRunner = Callable[
    [tuple[str, ...], dict[str, str], Path],
    SetupProcessResult,
]


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


def runtime_backend_for_recipe(runtime: RuntimeRecipe) -> RuntimeBackend:
    if runtime.backend == "host-nix":
        return HostNixRuntimeBackend()
    if runtime.backend == "container":
        return ContainerRuntimeBackend()
    raise ConfigError(f"unsupported runtime backend {runtime.backend}")


class HostNixRuntimeBackend:
    def __init__(self, setup_runner: SetupCommandRunner | None = None) -> None:
        self._setup_runner = setup_runner or _run_setup_command

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
            setup_results=tuple(setup_results),
        )


class ContainerRuntimeBackend:
    def __init__(self, setup_runner: SetupCommandRunner | None = None) -> None:
        self._setup_runner = setup_runner or _run_setup_command

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
            setup_results=tuple(setup_results),
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
) -> list[RuntimeSetupResult]:
    unsupported = unsupported_rigging_capability_reasons(
        resolution.runtime,
        resolution.riggings,
    )
    if unsupported:
        raise RuntimePreparationError("; ".join(unsupported))
    results = []
    for rigging in resolution.riggings:
        for step in rigging.install:
            setup_command = _setup_command(
                resolution.command,
                step,
            )
            if setup_command is None:
                continue
            argv = resolution.command_prefix + setup_command
            setup_result = setup_runner(argv, env, resolution.workspace_path)
            result = RuntimeSetupResult(
                origin="rigging",
                origin_name=rigging.name,
                action="install",
                target=step.target,
                argv=argv,
                exit_code=setup_result.exit_code,
                stdout=setup_result.stdout,
                stderr=setup_result.stderr,
            )
            results.append(result)
            if result.exit_code != 0:
                raise RuntimePreparationError(
                    "failed to install rigging "
                    f"{rigging.name} target {step.target}: {result.stderr.strip()}"
                )
    return results


def _setup_command(
    command: tuple[str, ...],
    step: RiggingInstallStep,
) -> tuple[str, ...] | None:
    method = step.method
    if method == "preinstalled":
        return None
    if method != "agent-extension":
        raise RuntimePreparationError(
            f"rigging install method {method} is not executable yet"
        )
    if not command:
        raise RuntimePreparationError("runtime command must not be empty")
    return (command[0], "install", step.target)


def _run_setup_command(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> SetupProcessResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=subprocess_env(argv, env),
        capture_output=True,
        check=False,
        text=True,
    )
    return SetupProcessResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
