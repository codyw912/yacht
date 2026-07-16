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
from yacht.harnesses.mcp_config import (
    McpConfigError,
    McpConfigRender,
    render_mcp_config,
)
from yacht.reports.surface_metadata import harness_for_runtime
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
class RiggingSetupFile:
    origin_name: str
    target: str
    content: str


@dataclass(frozen=True)
class RiggingSetupPlan:
    commands: tuple[RiggingSetupCommand, ...]
    files: tuple[RiggingSetupFile, ...] = ()
    mcp_config: McpConfigRender | None = None


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
    files = []
    mcp_steps = []
    for rigging in riggings:
        for step in rigging.install:
            if step.method == "config-file":
                files.append(_setup_file(rigging=rigging, step=step))
                continue
            if step.method == "mcp-server":
                mcp_steps.append((rigging.name, step))
                continue
            command = _setup_command(
                runtime=runtime,
                rigging=rigging,
                step=step,
                command_prefix=command_prefix,
            )
            if command is not None:
                commands.append(command)
    return RiggingSetupPlan(
        commands=tuple(commands),
        files=tuple(files),
        mcp_config=_mcp_config(runtime, tuple(mcp_steps)),
    )


def apply_rigging_setup(
    *,
    plan: RiggingSetupPlan,
    env: dict[str, str],
    workspace_path: Path,
    setup_runner: SetupCommandRunner,
    temp_home: Path,
) -> tuple[RuntimeSetupResult, ...]:
    results = []
    for setup_file in plan.files:
        results.append(_write_setup_file(setup_file, temp_home))
    if plan.mcp_config is not None:
        results.extend(_write_mcp_config(plan.mcp_config, temp_home))
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


def _setup_file(
    *,
    rigging: RiggingRecipe,
    step: RiggingInstallStep,
) -> RiggingSetupFile:
    if step.content is None:
        raise RiggingSetupError(f"config-file install {step.target} is missing content")
    return RiggingSetupFile(
        origin_name=rigging.name,
        target=step.target,
        content=step.content,
    )


def _write_setup_file(
    setup_file: RiggingSetupFile,
    temp_home: Path,
) -> RuntimeSetupResult:
    destination = _write_into_trial_home(
        target=setup_file.target,
        content=setup_file.content,
        temp_home=temp_home,
    )
    return RuntimeSetupResult(
        origin="rigging",
        origin_name=setup_file.origin_name,
        action="config-file",
        target=setup_file.target,
        argv=(),
        exit_code=0,
        stdout=f"wrote {destination}",
        stderr="",
    )


def _mcp_config(
    runtime: RuntimeRecipe,
    mcp_steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> McpConfigRender | None:
    if not mcp_steps:
        return None
    try:
        render = render_mcp_config(harness_for_runtime(runtime), mcp_steps)
    except McpConfigError as error:
        raise RiggingSetupError(str(error)) from error
    if render is None:
        raise RiggingSetupError(
            f"runtime harness {harness_for_runtime(runtime)} does not support "
            "rigging install method mcp-server yet"
        )
    return render


def _write_mcp_config(
    render: McpConfigRender,
    temp_home: Path,
) -> tuple[RuntimeSetupResult, ...]:
    destination = _write_into_trial_home(
        target=render.target,
        content=render.content,
        temp_home=temp_home,
    )
    return tuple(
        RuntimeSetupResult(
            origin="rigging",
            origin_name=entry.origin_name,
            action="mcp-server",
            target=entry.server_name,
            argv=(),
            exit_code=0,
            stdout=f"wrote {destination}",
            stderr="",
        )
        for entry in render.entries
    )


def _write_into_trial_home(
    *,
    target: str,
    content: str,
    temp_home: Path,
) -> Path:
    home = temp_home.resolve()
    destination = (home / target).resolve()
    if not destination.is_relative_to(home):
        raise RiggingSetupError(
            f"config-file install target {target} escapes the trial home"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


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
    if step.method == "package":
        if not step.target.startswith("npm:"):
            raise RiggingSetupError(
                f"package install target {step.target} is not supported yet"
            )
        package_name = step.target.removeprefix("npm:")
        return RiggingSetupCommand(
            origin_name=rigging.name,
            target=step.target,
            argv=command_prefix + ("npm", "install", "-g", package_name),
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
