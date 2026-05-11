from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.host_nix_runtime import HostNixRuntimeResolutionError
from yacht.host_nix_runtime import resolve_host_nix_runtime
from yacht.regatta import (
    Comparison,
    ConfigError,
    Regatta,
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
    trial_root = logbook_dir / "runtime" / comparison.name / vessel.name
    try:
        resolution = resolve_host_nix_runtime(
            regatta=regatta,
            vessel=vessel,
            instance_root=trial_root,
            workspace_path=workspace_path,
        )
    except HostNixRuntimeResolutionError as error:
        raise ConfigError(str(error)) from error

    return {
        "name": vessel.name,
        "runtime": resolution.runtime.name,
        "backend": resolution.runtime.backend,
        "trial_root": str(resolution.instance_root),
        "temp_home": str(resolution.temp_home),
        "workspace_path": str(resolution.workspace_path),
        "command_prefix": list(resolution.command_prefix),
        "command": list(resolution.command),
        "env": resolution.env_with_secret_placeholders(regatta),
        "secret_refs": list(resolution.secret_refs(regatta)),
        "cleanup_paths": [str(path) for path in resolution.cleanup_paths],
    }


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison references undefined vessel {name}")
