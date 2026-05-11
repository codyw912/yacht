from __future__ import annotations

from pathlib import Path
from typing import Protocol

from yacht.host_nix_runtime import HostNixRuntimeResolutionError
from yacht.host_nix_runtime import resolve_host_nix_runtime
from yacht.regatta import (
    Regatta,
    RuntimeInstance,
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

        return RuntimeInstance(
            runtime=resolution.runtime,
            temp_home=resolution.temp_home,
            workspace_path=resolution.workspace_path,
            env=env,
            command_prefix=resolution.command_prefix,
            cleanup_paths=resolution.cleanup_paths,
        )


def _create_runtime_dirs(temp_home: Path) -> None:
    for path in (
        temp_home,
        temp_home / ".config",
        temp_home / ".cache",
        temp_home / ".local" / "state",
    ):
        path.mkdir(parents=True, exist_ok=True)
