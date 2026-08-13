"""Parse Codex `exec --json` stdout.

The event types and usage field names come from a captured
`codex exec --json --ephemeral` stream. Skill stages stay empty until
a native skill event is captured.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from yacht.domain.model import Metrics, RuntimeInstance, Task
from yacht.preflight import AgentPromptResult, AgentPromptRunner, CommandResult
from yacht.runtimes.process import subprocess_env
from yacht.workflows.task_attempts import AgentTaskResult


CODEX_JSONL_EVENT_TYPES = frozenset(
    (
        "thread.started",
        "turn.started",
        "item.completed",
        "turn.completed",
        "turn.failed",
        "error",
    )
)


class CodexAdapterNotConfigured(ValueError):
    """Raised when Codex execution is requested without a launcher."""


class CodexStreamJsonError(ValueError):
    """Raised when a successful Codex task lacks complete JSONL evidence."""


CODEX_HEADLESS_FLAGS = ("exec", "--json", "--ephemeral")


@dataclass(frozen=True)
class CodexPromptRequest:
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


@dataclass(frozen=True)
class CodexTaskRequest:
    task_id: str
    task_title: str
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


CodexPromptLauncher = Callable[[CodexPromptRequest], AgentPromptResult]
CodexTaskLauncher = Callable[[CodexTaskRequest], AgentTaskResult]
CodexSubprocessRunner = Callable[[CodexPromptRequest], CommandResult]
CodexTaskSubprocessRunner = Callable[[CodexTaskRequest], CommandResult]
CodexVersionRunner = Callable[[tuple[str, ...], dict[str, str], Path], CommandResult]


class CodexAdapter:
    def __init__(
        self,
        launcher: CodexPromptLauncher | None = None,
        task_launcher: CodexTaskLauncher | None = None,
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
                transcript_path=transcript_dir / "codex-headless-prompt.json",
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
            raise CodexAdapterNotConfigured(
                "Codex headless prompt launcher is not configured"
            )
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        return self._launcher(
            CodexPromptRequest(
                prompt=prompt,
                argv=instance.command_prefix
                + instance.runtime.command
                + CODEX_HEADLESS_FLAGS,
                env=env,
                cwd=cwd,
                transcript_path=transcript_path,
            )
        )

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
            raise CodexAdapterNotConfigured("Codex task launcher is not configured")
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        return self._task_launcher(
            CodexTaskRequest(
                task_id=task.id,
                task_title=task.title,
                prompt=prompt,
                argv=instance.command_prefix
                + instance.runtime.command
                + CODEX_HEADLESS_FLAGS,
                env=env,
                cwd=cwd,
                transcript_path=transcript_path,
            )
        )


class SubprocessCodexPromptLauncher:
    def __init__(
        self,
        runner: CodexSubprocessRunner | None = None,
        version_runner: CodexVersionRunner | None = None,
    ) -> None:
        self._runner = runner or _run_codex_subprocess
        self._version_runner = version_runner or _run_codex_version

    def __call__(self, request: CodexPromptRequest) -> AgentPromptResult:
        result = self._runner(request)
        evidence = parse_codex_jsonl(result.stdout)
        harness_version = _captured_version(request, self._version_runner)
        response = str(evidence["response"]) if evidence else result.stdout
        tool_calls = _tool_calls_from_evidence(evidence)
        _write_transcript(
            request=request,
            result=result,
            response=response,
            tool_calls=tool_calls,
            harness_version=harness_version,
        )
        return AgentPromptResult(
            exit_code=result.exit_code,
            response=response,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
        )


class SubprocessCodexTaskLauncher:
    def __init__(
        self,
        runner: CodexTaskSubprocessRunner | None = None,
        version_runner: CodexVersionRunner | None = None,
    ) -> None:
        self._runner = runner or _run_codex_task_subprocess
        self._version_runner = version_runner or _run_codex_version

    def __call__(self, request: CodexTaskRequest) -> AgentTaskResult:
        started_at = time.perf_counter()
        result = self._runner(request)
        duration_seconds = round(time.perf_counter() - started_at, 3)
        evidence = parse_codex_jsonl(result.stdout)
        harness_version = _captured_version(request, self._version_runner)
        if result.exit_code == 0 and evidence is None:
            raise CodexStreamJsonError(
                f"codex task {request.task_id} exited 0 without a complete JSONL stream"
            )
        response = str(evidence["response"]) if evidence else result.stdout
        tool_calls = _tool_calls_from_evidence(evidence)
        _write_transcript(
            request=request,
            result=result,
            response=response,
            tool_calls=tool_calls,
            duration_seconds=duration_seconds,
            harness_version=harness_version,
        )
        return AgentTaskResult(
            exit_code=result.exit_code,
            response=response,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
            metrics=Metrics(
                tokens=_tokens(evidence),
                duration_seconds=duration_seconds,
                usage_source=_usage_source(evidence),
            ),
            machine_evidence=_machine_evidence(evidence, harness_version),
        )


def _run_codex_subprocess(request: CodexPromptRequest) -> CommandResult:
    return _run_codex_command(
        argv=request.argv, cwd=request.cwd, env=request.env, prompt=request.prompt
    )


def _run_codex_task_subprocess(request: CodexTaskRequest) -> CommandResult:
    return _run_codex_command(
        argv=request.argv, cwd=request.cwd, env=request.env, prompt=request.prompt
    )


def _run_codex_command(
    *, argv: tuple[str, ...], cwd: Path, env: dict[str, str], prompt: str
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
        exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def _run_codex_version(
    argv: tuple[str, ...], env: dict[str, str], cwd: Path
) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=subprocess_env(argv, env),
        input=None,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def _captured_version(
    request: CodexPromptRequest | CodexTaskRequest, runner: CodexVersionRunner
) -> str | None:
    argv = request.argv[: -len(CODEX_HEADLESS_FLAGS)] + ("--version",)
    result = runner(argv, request.env, request.cwd)
    if result.exit_code != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _write_transcript(
    *,
    request: CodexPromptRequest | CodexTaskRequest,
    result: CommandResult,
    response: str,
    tool_calls: tuple[str, ...],
    duration_seconds: float | None = None,
    harness_version: str | None = None,
) -> None:
    transcript: dict[str, Any] = {
        "argv": list(request.argv),
        "cwd": str(request.cwd),
        "exit_code": result.exit_code,
        "prompt": request.prompt,
        "response": response,
        "stderr": result.stderr,
        "stdout": result.stdout,
        "tool_calls": list(tool_calls),
    }
    if isinstance(request, CodexTaskRequest):
        transcript["task_id"] = request.task_id
        transcript["task_title"] = request.task_title
    if duration_seconds is not None:
        transcript["duration_seconds"] = duration_seconds
    evidence = parse_codex_jsonl(result.stdout)
    machine_evidence = _machine_evidence(evidence, harness_version)
    if machine_evidence:
        transcript["machine_evidence"] = machine_evidence
    request.transcript_path.write_text(
        json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _machine_evidence(
    evidence: dict[str, Any] | None, harness_version: str | None = None
) -> dict[str, Any]:
    machine_evidence: dict[str, Any] = {"format": "codex-jsonl"}
    if evidence is not None:
        machine_evidence.update(evidence)
    if harness_version is not None:
        machine_evidence["harness_version"] = harness_version
    return machine_evidence


def _tool_calls_from_evidence(evidence: dict[str, Any] | None) -> tuple[str, ...]:
    if evidence is None:
        return ()
    tool_calls = evidence.get("tool_calls")
    if not isinstance(tool_calls, tuple):
        return ()
    return tool_calls


def _tokens(evidence: dict[str, Any] | None) -> int:
    if evidence is None:
        return 0
    usage = evidence.get("usage")
    if not isinstance(usage, dict):
        return 0
    return sum(value for value in usage.values() if isinstance(value, int))


def _usage_source(evidence: dict[str, Any] | None) -> str:
    if evidence is None:
        return "unreported"
    return str(evidence["usage_source"])


def parse_codex_jsonl(output: str) -> dict[str, Any] | None:
    events = _jsonl_events(output)
    if not events or not _looks_like_codex_jsonl(events):
        return None
    if not any(event.get("type") == "turn.started" for event in events):
        return None
    if not any(
        event.get("type") in {"turn.completed", "turn.failed"} for event in events
    ):
        return None
    usage = _usage(events)
    parsed: dict[str, Any] = {
        "response": _response(events),
        "usage_source": "reported" if usage else "unreported",
        "skill_stages": (),
        "tool_calls": _tool_calls(events),
        "ended": _ended(events),
    }
    if usage:
        parsed["usage"] = usage
    return parsed


def _looks_like_codex_jsonl(events: list[dict[str, Any]]) -> bool:
    return any(event.get("type") in CODEX_JSONL_EVENT_TYPES for event in events)


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


def _response(events: list[dict[str, Any]]) -> str:
    text = ""
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        value = item.get("text")
        if isinstance(value, str):
            text = value
    return text


def _usage(events: list[dict[str, Any]]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for event in events:
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        mapping = (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("cached_input_tokens", "cache_read_tokens"),
            ("cache_write_input_tokens", "cache_write_tokens"),
        )
        for source, dest in mapping:
            value = usage.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                parsed[dest] = value
    return parsed


def _ended(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        event_type = event.get("type")
        if event_type in {"turn.failed", "error"}:
            return "error"
        if event_type == "turn.completed":
            return "natural"
    return "unmeasured"


def _tool_calls(events: list[dict[str, Any]]) -> tuple[str, ...]:
    names: list[str] = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            names.append("command_execution")
    return tuple(dict.fromkeys(names))
