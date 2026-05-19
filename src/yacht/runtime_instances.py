from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.container_runtime import ContainerRuntimeResolutionError
from yacht.container_runtime import resolve_container_runtime
from yacht.host_nix_runtime import HostNixRuntimeResolutionError
from yacht.host_nix_runtime import resolve_host_nix_runtime
from yacht.regatta import (
    Comparison,
    ConfigError,
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    Vessel,
    load_regatta,
)
from yacht.runtime_capabilities import rigging_capabilities_to_json
from yacht.schemas import RUNTIME_INSTANCES_SCHEMA
from yacht.schemas import validate_runtime_instances_document
from yacht.surface_metadata import agent_for_runtime
from yacht.surface_metadata import regatta_surfaces_to_json
from yacht.surface_metadata import vessel_surfaces_to_json


RUNTIME_INSTANCES_PLAN_PATH = Path("runtime-instances.json")


def build_runtime_instances_plan(
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    if not regatta.comparisons:
        raise ConfigError("runtime instances require at least one comparison")
    return {
        "schema": RUNTIME_INSTANCES_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "surfaces": regatta_surfaces_to_json(regatta),
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


def write_runtime_instances_plan(
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    plan = build_runtime_instances_plan(config_path, logbook_dir, workspace_path)
    validate_runtime_instances_document(plan)
    _write_json(logbook_dir / RUNTIME_INSTANCES_PLAN_PATH, plan)
    return plan


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
        runtime = _runtime_for_vessel(regatta, vessel)
        riggings = _riggings_for_vessel(regatta, vessel)
        if runtime.backend == "host-nix":
            resolution = resolve_host_nix_runtime(
                regatta=regatta,
                vessel=vessel,
                instance_root=trial_root,
                workspace_path=workspace_path,
            )
        elif runtime.backend == "container":
            resolution = resolve_container_runtime(
                regatta=regatta,
                vessel=vessel,
                instance_root=trial_root,
                workspace_path=workspace_path,
            )
        else:
            raise ConfigError(f"unsupported runtime backend {runtime.backend}")
    except (ContainerRuntimeResolutionError, HostNixRuntimeResolutionError) as error:
        raise ConfigError(str(error)) from error

    payload = {
        "name": vessel.name,
        "runtime": resolution.runtime.name,
        "backend": resolution.runtime.backend,
        "agent": agent_for_runtime(resolution.runtime),
        "surfaces": vessel_surfaces_to_json(resolution.runtime, riggings),
        "rigging_capabilities": rigging_capabilities_to_json(
            resolution.runtime,
            riggings,
        ),
        "install": [
            step.to_json()
            for rigging in riggings
            for step in rigging.install
        ],
        "trial_root": str(resolution.instance_root),
        "temp_home": str(resolution.temp_home),
        "workspace_path": str(resolution.workspace_path),
        "command_prefix": list(resolution.command_prefix),
        "command": list(resolution.command),
        "env": resolution.env_with_secret_placeholders(regatta),
        "secret_refs": list(resolution.secret_refs(regatta)),
        "cleanup_paths": [str(path) for path in resolution.cleanup_paths],
    }
    if resolution.runtime.image is not None:
        payload["image"] = resolution.runtime.image
    if resolution.runtime.backend == "container":
        payload["container_home"] = resolution.runtime.container_home
        payload["container_workspace"] = resolution.runtime.container_workspace
    return payload


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(f"vessel {vessel.name} does not define a runtime")
    return regatta.runtime_recipes[vessel.runtime]


def _riggings_for_vessel(
    regatta: Regatta,
    vessel: Vessel,
) -> tuple[RiggingRecipe, ...]:
    return tuple(regatta.rigging_recipes[name] for name in vessel.rigging)


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison references undefined vessel {name}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
