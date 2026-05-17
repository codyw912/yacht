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
    parse_agent_response_json,
)
from yacht.regatta import Metrics, RuntimeInstance, Task
from yacht.runtime_process import subprocess_env
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
PI_JSONL_EVENT_TYPES = frozenset(
    (
        "session",
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    )
)


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
        machine_evidence = _pi_jsonl_machine_evidence(result.stdout)
        tool_calls = _tool_calls_from_machine_evidence(
            machine_evidence,
        ) or _tool_calls_from_output(result.stdout)
        response = _response_from_pi_jsonl(result.stdout) or result.stdout
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


class SubprocessPiTaskLauncher:
    def __init__(self, runner: PiTaskSubprocessRunner | None = None) -> None:
        self._runner = runner or _run_pi_task_subprocess

    def __call__(self, request: PiTaskRequest) -> AgentTaskResult:
        started_at = time.perf_counter()
        result = self._runner(request)
        duration_seconds = round(time.perf_counter() - started_at, 3)
        machine_evidence = _pi_jsonl_machine_evidence(result.stdout)
        tool_calls = _tool_calls_from_machine_evidence(
            machine_evidence,
        ) or _tool_calls_from_output(result.stdout)
        response = _response_from_pi_jsonl(result.stdout) or result.stdout
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
                tokens=_tokens_from_machine_evidence(
                    machine_evidence,
                )
                or _estimated_tokens(request.prompt, result.stdout),
                duration_seconds=duration_seconds,
            ),
            machine_evidence=machine_evidence,
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


def _tool_calls_from_output(output: str) -> tuple[str, ...]:
    payload = parse_agent_response_json(output)
    if payload is None:
        return ()

    tool_calls = payload.get("tool_calls", ())
    if not isinstance(tool_calls, list):
        return ()
    return tuple(tool_call for tool_call in tool_calls if isinstance(tool_call, str))


def _pi_jsonl_machine_evidence(output: str) -> dict[str, Any]:
    events = _jsonl_events(output)
    if not events or not _looks_like_pi_jsonl(events):
        return {}

    assistant_message = _last_assistant_message(events)
    usage = _usage_without_cost(assistant_message)
    cost = _usage_cost(assistant_message)
    tool_calls = _tool_calls_from_pi_events(events)

    evidence: dict[str, Any] = {
        "format": "pi-jsonl",
        "event_count": len(events),
    }
    for source_key, evidence_key in (
        ("api", "api"),
        ("provider", "provider"),
        ("model", "model"),
        ("responseId", "response_id"),
    ):
        value = assistant_message.get(source_key)
        if isinstance(value, str) and value:
            evidence[evidence_key] = value
    if usage:
        evidence["usage"] = usage
    if cost:
        evidence["cost"] = cost
    if tool_calls:
        evidence["tool_calls"] = list(tool_calls)
    return evidence


def _looks_like_pi_jsonl(events: list[dict[str, Any]]) -> bool:
    return any(
        event.get("type") in PI_JSONL_EVENT_TYPES
        or isinstance(event.get("toolResults"), list)
        or isinstance(event.get("tool_results"), list)
        or _message_has_pi_metadata(event.get("message"))
        for event in events
    )


def _message_has_pi_metadata(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(isinstance(value.get(key), str) for key in ("api", "provider", "model"))


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


def _last_assistant_message(events: list[dict[str, Any]]) -> dict[str, Any]:
    assistant_messages = [
        message
        for event in events
        if isinstance((message := event.get("message")), dict)
        and message.get("role") == "assistant"
    ]
    if not assistant_messages:
        return {}
    return assistant_messages[-1]


def _response_from_pi_jsonl(output: str) -> str:
    events = _jsonl_events(output)
    if not events or not _looks_like_pi_jsonl(events):
        return ""
    return _text_from_message(_last_assistant_message(events))


def _text_from_message(message: dict[str, Any]) -> str:
    text_parts: list[str] = []
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return "".join(text_parts)


def _usage_without_cost(message: dict[str, Any]) -> dict[str, Any]:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {
        key: value
        for key, value in usage.items()
        if key != "cost" and isinstance(value, int | float)
    }


def _usage_cost(message: dict[str, Any]) -> dict[str, Any]:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return {}
    cost = usage.get("cost")
    if not isinstance(cost, dict):
        return {}
    return {
        key: value
        for key, value in cost.items()
        if isinstance(value, int | float)
    }


def _tool_calls_from_pi_events(events: list[dict[str, Any]]) -> tuple[str, ...]:
    tool_calls: list[str] = []
    for event in events:
        for tool_result in _tool_result_values(event):
            name = _tool_name(tool_result)
            if name is not None:
                tool_calls.append(name)
    return tuple(dict.fromkeys(tool_calls))


def _tool_result_values(event: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for key in ("toolResults", "tool_results"):
        value = event.get(key)
        if isinstance(value, list):
            values.extend(value)
    return values


def _tool_name(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if not isinstance(value, dict):
        return None
    for key in ("toolName", "tool_name", "name"):
        name = value.get(key)
        if isinstance(name, str) and name:
            return name
    return None


def _tool_calls_from_machine_evidence(
    machine_evidence: dict[str, Any],
) -> tuple[str, ...]:
    tool_calls = machine_evidence.get("tool_calls")
    if not isinstance(tool_calls, list):
        return ()
    return tuple(tool_call for tool_call in tool_calls if isinstance(tool_call, str))


def _tokens_from_machine_evidence(machine_evidence: dict[str, Any]) -> int | None:
    usage = machine_evidence.get("usage")
    if not isinstance(usage, dict):
        return None
    tokens = usage.get("totalTokens")
    if not isinstance(tokens, int) or tokens < 0:
        return None
    return tokens


def _estimated_tokens(prompt: str, output: str) -> int:
    return len(prompt.split()) + len(output.split())
