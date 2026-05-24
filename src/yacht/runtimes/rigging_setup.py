from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yacht.domain.model import (
    RiggingInstallStep,
    RiggingRecipe,
    RuntimeRecipe,
    RuntimeSetupResult,
)
from yacht.runtimes.capabilities import unsupported_rigging_capability_reasons
from yacht.runtimes.process import subprocess_env


class RiggingSetupError(ValueError):
    """Raised when runtime rigging cannot be planned or applied."""


@dataclass(frozen=True)
class SetupProcessResult:
    exit_code: int
    stdout: str
    stderr: str


SetupCommandRunner = Callable[
    [tuple[str, ...], dict[str, str], Path],
    SetupProcessResult,
]


@dataclass(frozen=True)
class RiggingSetupCommand:
    origin_name: str
    target: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class RiggingSetupPlan:
    commands: tuple[RiggingSetupCommand, ...]


def plan_rigging_setup(
    *,
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    command_prefix: tuple[str, ...],
) -> RiggingSetupPlan:
    unsupported = unsupported_rigging_capability_reasons(runtime, riggings)
    if unsupported:
        raise RiggingSetupError("; ".join(unsupported))

    commands = []
    for rigging in riggings:
        for step in rigging.install:
            command = _setup_command(
                runtime=runtime,
                rigging=rigging,
                step=step,
                command_prefix=command_prefix,
            )
            if command is not None:
                commands.append(command)
    return RiggingSetupPlan(commands=tuple(commands))


def apply_rigging_setup(
    *,
    plan: RiggingSetupPlan,
    env: dict[str, str],
    workspace_path: Path,
    setup_runner: SetupCommandRunner,
) -> tuple[RuntimeSetupResult, ...]:
    results = []
    for command in plan.commands:
        setup_result = setup_runner(command.argv, env, workspace_path)
        result = RuntimeSetupResult(
            origin="rigging",
            origin_name=command.origin_name,
            action="install",
            target=command.target,
            argv=command.argv,
            exit_code=setup_result.exit_code,
            stdout=setup_result.stdout,
            stderr=setup_result.stderr,
        )
        results.append(result)
        if result.exit_code != 0:
            raise RiggingSetupError(
                "failed to install rigging "
                f"{command.origin_name} target {command.target}: "
                f"{result.stderr.strip()}"
            )
    return tuple(results)


def run_setup_command(
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


def _setup_command(
    *,
    runtime: RuntimeRecipe,
    rigging: RiggingRecipe,
    step: RiggingInstallStep,
    command_prefix: tuple[str, ...],
) -> RiggingSetupCommand | None:
    if step.method == "preinstalled":
        return None
    if step.method == "custom-command":
        if not step.command:
            raise RiggingSetupError("custom-command install requires command")
        return RiggingSetupCommand(
            origin_name=rigging.name,
            target=step.target,
            argv=command_prefix + step.command,
        )
    if step.method != "agent-extension":
        raise RiggingSetupError(
            f"rigging install method {step.method} is not executable yet"
        )
    if not runtime.command:
        raise RiggingSetupError("runtime command must not be empty")
    return RiggingSetupCommand(
        origin_name=rigging.name,
        target=step.target,
        argv=command_prefix + (runtime.command[0], "install", step.target),
    )
