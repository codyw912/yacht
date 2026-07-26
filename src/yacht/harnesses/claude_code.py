from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from yacht.preflight import (
    AgentPromptResult,
    AgentPromptRunner,
    CommandResult,
)
from yacht.domain.model import ConfigError, Metrics, RuntimeInstance, Task
from yacht.runtimes.process import subprocess_env
from yacht.workflows.task_attempts import AgentTaskResult


class ClaudeCodeAdapterNotConfigured(ValueError):
    """Raised when Claude Code execution is requested without a launcher."""


class ClaudeCodeStreamJsonError(ValueError):
    """Raised when Claude Code output does not carry usable machine evidence."""


HEADLESS_FLAGS = ("--print", "--output-format", "stream-json", "--verbose")
PERMISSION_BYPASS_FLAG = "--dangerously-skip-permissions"


@dataclass(frozen=True)
class ClaudeCodePromptRequest:
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


@dataclass(frozen=True)
class ClaudeCodeTaskRequest:
    task_id: str
    task_title: str
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


ClaudeCodePromptLauncher = Callable[[ClaudeCodePromptRequest], AgentPromptResult]
ClaudeCodeTaskLauncher = Callable[[ClaudeCodeTaskRequest], AgentTaskResult]
ClaudeCodeSubprocessRunner = Callable[[ClaudeCodePromptRequest], CommandResult]
ClaudeCodeTaskSubprocessRunner = Callable[[ClaudeCodeTaskRequest], CommandResult]


class ClaudeCodeAdapter:
    def __init__(
        self,
        launcher: ClaudeCodePromptLauncher | None = None,
        task_launcher: ClaudeCodeTaskLauncher | None = None,
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
                transcript_path=transcript_dir / "claude-code-headless-prompt.json",
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
            raise ClaudeCodeAdapterNotConfigured(
                "Claude Code headless prompt launcher is not configured"
            )

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request = ClaudeCodePromptRequest(
            prompt=prompt,
            argv=instance.command_prefix + instance.runtime.command + HEADLESS_FLAGS,
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
            raise ClaudeCodeAdapterNotConfigured(
                "Claude Code task launcher is not configured"
            )
        if instance.runtime.backend != "container":
            raise ConfigError(
                f"claude-code task attempts run with {PERMISSION_BYPASS_FLAG}, "
                "which is only allowed inside an isolated container runtime: "
                f"runtime {instance.runtime.name} uses backend "
                f"{instance.runtime.backend}"
            )

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request = ClaudeCodeTaskRequest(
            task_id=task.id,
            task_title=task.title,
            prompt=prompt,
            argv=(
                instance.command_prefix
                + instance.runtime.command
                + HEADLESS_FLAGS
                + (PERMISSION_BYPASS_FLAG,)
            ),
            env=env,
            cwd=cwd,
            transcript_path=transcript_path,
        )
        return self._task_launcher(request)


class SubprocessClaudeCodePromptLauncher:
    def __init__(self, runner: ClaudeCodeSubprocessRunner | None = None) -> None:
        self._runner = runner or _run_claude_code_subprocess

    def __call__(self, request: ClaudeCodePromptRequest) -> AgentPromptResult:
        result = self._runner(request)
        machine_evidence = _stream_json_machine_evidence(result.stdout)
        tool_calls = _tool_calls_from_machine_evidence(machine_evidence)
        response = _response_from_machine_evidence(machine_evidence) or result.stdout
        request.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript: dict[str, Any] = {
            "prompt": request.prompt,
            "argv": list(request.argv),
            "cwd": str(request.cwd),
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "response": response,
            "stderr": result.stderr,
            "tool_calls": list(tool_calls),
        }
        if machine_evidence:
            transcript["machine_evidence"] = machine_evidence
        request.transcript_path.write_text(
            json.dumps(transcript, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return AgentPromptResult(
            exit_code=result.exit_code,
            response=response,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
        )


class SubprocessClaudeCodeTaskLauncher:
    def __init__(self, runner: ClaudeCodeTaskSubprocessRunner | None = None) -> None:
        self._runner = runner or _run_claude_code_task_subprocess

    def __call__(self, request: ClaudeCodeTaskRequest) -> AgentTaskResult:
        started_at = time.perf_counter()
        result = self._runner(request)
        duration_seconds = round(time.perf_counter() - started_at, 3)
        machine_evidence = _stream_json_machine_evidence(result.stdout)
        tokens = _tokens_from_machine_evidence(machine_evidence)
        if result.exit_code == 0 and tokens is None:
            raise ClaudeCodeStreamJsonError(
                f"claude-code task {request.task_id} exited 0 without a valid "
                "stream-json result message; refusing to record the attempt "
                "with partial machine evidence"
            )
        tool_calls = _tool_calls_from_machine_evidence(machine_evidence)
        response = _response_from_machine_evidence(machine_evidence) or result.stdout
        request.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript: dict[str, Any] = {
            "task_id": request.task_id,
            "task_title": request.task_title,
            "prompt": request.prompt,
            "argv": list(request.argv),
            "cwd": str(request.cwd),
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "response": response,
            "stderr": result.stderr,
            "tool_calls": list(tool_calls),
            "duration_seconds": duration_seconds,
        }
        if machine_evidence:
            transcript["machine_evidence"] = machine_evidence
        request.transcript_path.write_text(
            json.dumps(transcript, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return AgentTaskResult(
            exit_code=result.exit_code,
            response=response,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
            metrics=Metrics(
                tokens=(
                    tokens
                    if tokens is not None
                    else _estimated_tokens(request.prompt, result.stdout)
                ),
                duration_seconds=duration_seconds,
                usage_source="reported" if tokens is not None else "estimated",
            ),
            machine_evidence=machine_evidence,
        )


def _run_claude_code_subprocess(request: ClaudeCodePromptRequest) -> CommandResult:
    return _run_claude_code_command(
        argv=request.argv,
        cwd=request.cwd,
        env=request.env,
        prompt=request.prompt,
    )


def _run_claude_code_task_subprocess(request: ClaudeCodeTaskRequest) -> CommandResult:
    return _run_claude_code_command(
        argv=request.argv,
        cwd=request.cwd,
        env=request.env,
        prompt=request.prompt,
    )


def _run_claude_code_command(
    *,
    argv: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    prompt: str,
) -> CommandResult:
    completed = subprocess.run(
        argv + (prompt,),
        cwd=cwd,
        env=subprocess_env(argv, env),
        input=None,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _stream_json_machine_evidence(output: str) -> dict[str, Any]:
    events = _jsonl_events(output)
    if not events or not _looks_like_claude_stream_json(events):
        return {}

    result_event = _result_event(events)
    evidence: dict[str, Any] = {
        "format": "claude-code-stream-json",
        "event_count": len(events),
    }
    model = _model_from_events(events)
    if model:
        evidence["model"] = model
    for source_key, evidence_key in (
        ("session_id", "session_id"),
        ("subtype", "subtype"),
    ):
        value = result_event.get(source_key)
        if isinstance(value, str) and value:
            evidence[evidence_key] = value
    if isinstance(result_event.get("is_error"), bool):
        evidence["is_error"] = result_event["is_error"]
    for key in ("num_turns", "duration_ms", "duration_api_ms"):
        value = result_event.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            evidence[key] = value
    usage = _numeric_fields(result_event.get("usage"))
    if usage:
        evidence["usage"] = usage
    cost = result_event.get("total_cost_usd")
    if isinstance(cost, int | float) and not isinstance(cost, bool):
        evidence["cost"] = {"total": cost}
    result_text = result_event.get("result")
    if isinstance(result_text, str):
        evidence["result"] = result_text
    tool_calls = _tool_calls_from_events(events)
    if tool_calls:
        evidence["tool_calls"] = list(tool_calls)
    return evidence


def _looks_like_claude_stream_json(events: list[dict[str, Any]]) -> bool:
    return any(
        event.get("type") == "result"
        or (event.get("type") == "system" and event.get("subtype") == "init")
        for event in events
    )


def _jsonl_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(event, dict):
            return []
        events.append(event)
    return events


def _result_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "result":
            return event
    return {}


def _model_from_events(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            model = event.get("model")
            if isinstance(model, str) and model:
                return model
    return None


def _numeric_fields(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(item, int | float) and not isinstance(item, bool)
    }


def _tool_calls_from_events(events: list[dict[str, Any]]) -> tuple[str, ...]:
    tool_calls: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                tool_calls.append(name)
    return tuple(dict.fromkeys(tool_calls))


def _tool_calls_from_machine_evidence(
    machine_evidence: dict[str, Any],
) -> tuple[str, ...]:
    tool_calls = machine_evidence.get("tool_calls")
    if not isinstance(tool_calls, list):
        return ()
    return tuple(tool_call for tool_call in tool_calls if isinstance(tool_call, str))


def _response_from_machine_evidence(machine_evidence: dict[str, Any]) -> str:
    result_text = machine_evidence.get("result")
    if isinstance(result_text, str):
        return result_text
    return ""


TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _tokens_from_machine_evidence(machine_evidence: dict[str, Any]) -> int | None:
    usage = machine_evidence.get("usage")
    if not isinstance(usage, dict):
        return None
    counted = [
        value
        for field in TOKEN_USAGE_FIELDS
        if isinstance((value := usage.get(field)), int) and value >= 0
    ]
    if not counted:
        return None
    return sum(counted)


def _estimated_tokens(prompt: str, output: str) -> int:
    return len(prompt.split()) + len(output.split())
