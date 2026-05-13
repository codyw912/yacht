from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yacht.preflight import AgentPromptResult, AgentPromptRunner, CommandResult
from yacht.regatta import Metrics, RuntimeInstance, Task
from yacht.task_attempts import AgentTaskResult


class PiAdapterNotConfigured(ValueError):
    """Raised when Pi prompt execution is requested without a launcher."""


@dataclass(frozen=True)
class PiPromptRequest:
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


@dataclass(frozen=True)
class PiTaskRequest:
    task_id: str
    task_title: str
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


PiPromptLauncher = Callable[[PiPromptRequest], AgentPromptResult]
PiTaskLauncher = Callable[[PiTaskRequest], AgentTaskResult]
PiSubprocessRunner = Callable[[PiPromptRequest], CommandResult]
PiTaskSubprocessRunner = Callable[[PiTaskRequest], CommandResult]


class PiAdapter:
    def __init__(
        self,
        launcher: PiPromptLauncher | None = None,
        task_launcher: PiTaskLauncher | None = None,
    ) -> None:
        self._launcher = launcher
        self._task_launcher = task_launcher

    def agent_prompt_runner(
        self,
        *,
        instance: RuntimeInstance,
        transcript_dir: Path,
    ) -> AgentPromptRunner:
        def run(prompt: str, env: dict[str, str], cwd: Path) -> AgentPromptResult:
            return self.run_headless_prompt(
                prompt=prompt,
                instance=instance,
                env=env,
                cwd=cwd,
                transcript_path=transcript_dir / "pi-headless-prompt.json",
            )

        return run

    def run_headless_prompt(
        self,
        *,
        prompt: str,
        instance: RuntimeInstance,
        env: dict[str, str],
        cwd: Path,
        transcript_path: Path,
    ) -> AgentPromptResult:
        if self._launcher is None:
            raise PiAdapterNotConfigured(
                "Pi headless prompt launcher is not configured"
            )

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request = PiPromptRequest(
            prompt=prompt,
            argv=instance.command_prefix + instance.runtime.command,
            env=env,
            cwd=cwd,
            transcript_path=transcript_path,
        )
        return self._launcher(request)

    def run_task(
        self,
        *,
        instance: RuntimeInstance,
        task: Task,
        prompt: str,
        env: dict[str, str],
        cwd: Path,
        transcript_path: Path,
    ) -> AgentTaskResult:
        if self._task_launcher is None:
            raise PiAdapterNotConfigured("Pi task launcher is not configured")

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request = PiTaskRequest(
            task_id=task.id,
            task_title=task.title,
            prompt=prompt,
            argv=instance.command_prefix + instance.runtime.command,
            env=env,
            cwd=cwd,
            transcript_path=transcript_path,
        )
        return self._task_launcher(request)


class SubprocessPiPromptLauncher:
    def __init__(self, runner: PiSubprocessRunner | None = None) -> None:
        self._runner = runner or _run_pi_subprocess

    def __call__(self, request: PiPromptRequest) -> AgentPromptResult:
        result = self._runner(request)
        tool_calls = _tool_calls_from_output(result.stdout)
        request.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request.transcript_path.write_text(
            json.dumps(
                {
                    "prompt": request.prompt,
                    "argv": list(request.argv),
                    "cwd": str(request.cwd),
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "tool_calls": list(tool_calls),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return AgentPromptResult(
            exit_code=result.exit_code,
            response=result.stdout,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
        )


class SubprocessPiTaskLauncher:
    def __init__(self, runner: PiTaskSubprocessRunner | None = None) -> None:
        self._runner = runner or _run_pi_task_subprocess

    def __call__(self, request: PiTaskRequest) -> AgentTaskResult:
        result = self._runner(request)
        tool_calls = _tool_calls_from_output(result.stdout)
        request.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request.transcript_path.write_text(
            json.dumps(
                {
                    "task_id": request.task_id,
                    "task_title": request.task_title,
                    "prompt": request.prompt,
                    "argv": list(request.argv),
                    "cwd": str(request.cwd),
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "tool_calls": list(tool_calls),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return AgentTaskResult(
            exit_code=result.exit_code,
            response=result.stdout,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
            metrics=Metrics(
                tokens=_estimated_tokens(request.prompt, result.stdout),
                duration_seconds=0.0,
            ),
        )


def _run_pi_subprocess(request: PiPromptRequest) -> CommandResult:
    return _run_pi_command(
        argv=request.argv,
        cwd=request.cwd,
        env=request.env,
        prompt=request.prompt,
    )


def _run_pi_task_subprocess(request: PiTaskRequest) -> CommandResult:
    return _run_pi_command(
        argv=request.argv,
        cwd=request.cwd,
        env=request.env,
        prompt=request.prompt,
    )


def _run_pi_command(
    *,
    argv: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    prompt: str,
) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=prompt,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _tool_calls_from_output(output: str) -> tuple[str, ...]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, dict):
        return ()

    tool_calls = payload.get("tool_calls", ())
    if not isinstance(tool_calls, list):
        return ()
    return tuple(tool_call for tool_call in tool_calls if isinstance(tool_call, str))


def _estimated_tokens(prompt: str, output: str) -> int:
    return len(prompt.split()) + len(output.split())
