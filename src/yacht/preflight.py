from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yacht.regatta import (
    Comparison,
    PreflightCheck,
    Regatta,
    RiggingRecipe,
    RuntimeInstance,
    RuntimeRecipe,
    SecretReference,
    Vessel,
)
from yacht.schemas import PREFLIGHT_SCHEMA, validate_preflight_document


MACHINE_CHECK_KINDS = {"command", "env", "path-isolation"}


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class MachineCheck:
    check: PreflightCheck
    required: bool


CommandRunner = Callable[[tuple[str, ...], dict[str, str], Path], CommandResult]


def execute_machine_preflight(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance: RuntimeInstance,
    artifact_path: Path,
    comparison: Comparison | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    runner = command_runner or _run_command
    runtime = instance.runtime
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    checks = _machine_checks(runtime, riggings)
    check_results = [
        _execute_check(check, instance, runner)
        for check in checks
    ]
    artifact = {
        "schema": PREFLIGHT_SCHEMA,
        "regatta": regatta.name,
        "vessel": vessel.name,
        "runtime": runtime.name,
        "status": _artifact_status(check_results),
        "failure_policy": regatta.preflight.failure_policy,
        "secret_refs": [
            _secret_ref_to_json(name, regatta.secrets[name])
            for name in _required_secret_names(runtime, riggings)
        ],
        "checks": check_results,
    }
    if comparison is not None:
        artifact["comparison"] = comparison.name

    validate_preflight_document(artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def _run_command(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _machine_checks(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> list[MachineCheck]:
    checks = [
        MachineCheck(check=check, required=runtime.preflight.required and check.required)
        for check in runtime.preflight.checks
        if check.kind in MACHINE_CHECK_KINDS
    ]
    for rigging in riggings:
        checks.extend(
            MachineCheck(
                check=check,
                required=rigging.preflight.required and check.required,
            )
            for check in rigging.preflight.checks
            if check.kind in MACHINE_CHECK_KINDS
        )
    return checks


def _execute_check(
    machine_check: MachineCheck,
    instance: RuntimeInstance,
    command_runner: CommandRunner,
) -> dict[str, object]:
    check = machine_check.check
    if check.kind == "command":
        return _execute_command_check(machine_check, instance, command_runner)
    if check.kind == "env":
        return _execute_env_check(machine_check, instance)
    if check.kind == "path-isolation":
        return _execute_path_isolation_check(machine_check, instance)
    raise ValueError(f"unsupported machine preflight check kind {check.kind}")


def _execute_command_check(
    machine_check: MachineCheck,
    instance: RuntimeInstance,
    command_runner: CommandRunner,
) -> dict[str, object]:
    check = machine_check.check
    argv = instance.command_prefix + check.command
    result = command_runner(argv, instance.env, instance.workspace_path)
    return {
        "name": check.name,
        "kind": check.kind,
        "required": machine_check.required,
        "status": "passed" if result.exit_code == 0 else "failed",
        "evidence": {
            "argv": list(argv),
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }


def _execute_env_check(
    machine_check: MachineCheck,
    instance: RuntimeInstance,
) -> dict[str, object]:
    check = machine_check.check
    missing = [name for name in check.env if name not in instance.env]
    present = {
        name: instance.env[name]
        for name in check.env
        if name in instance.env
    }
    evidence: dict[str, object] = {"present_env": present}
    if missing:
        evidence["missing_env"] = missing
    return {
        "name": check.name,
        "kind": check.kind,
        "required": machine_check.required,
        "status": "failed" if missing else "passed",
        "evidence": evidence,
    }


def _execute_path_isolation_check(
    machine_check: MachineCheck,
    instance: RuntimeInstance,
) -> dict[str, object]:
    check = machine_check.check
    missing = [name for name in check.env if name not in instance.env]
    resolved_paths = {
        name: instance.env[name]
        for name in check.env
        if name in instance.env
    }
    outside_trial_home = {
        name: value
        for name, value in resolved_paths.items()
        if not _is_under(instance.temp_home, Path(value))
    }
    evidence: dict[str, object] = {"paths": resolved_paths}
    if missing:
        evidence["missing_env"] = missing
    if outside_trial_home:
        evidence["outside_trial_home"] = outside_trial_home
    status = "failed" if missing or outside_trial_home else "passed"
    return {
        "name": check.name,
        "kind": check.kind,
        "required": machine_check.required,
        "status": status,
        "evidence": evidence,
    }


def _is_under(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _artifact_status(checks: list[dict[str, object]]) -> str:
    for check in checks:
        if check["required"] and check["status"] != "passed":
            return "failed"
    return "passed"


def _required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


def _secret_ref_to_json(name: str, secret: SecretReference) -> dict[str, object]:
    ref = secret.name if secret.source == "env" else secret.path
    return {
        "name": name,
        "source": secret.source,
        "ref": ref,
        "redacted": True,
    }
