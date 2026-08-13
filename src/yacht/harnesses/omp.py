"""Parse OMP `--mode json` stdout.

The event types and usage field names come from a captured
`omp -p --mode json --no-session` stream. Skill stages stay empty until
a native skill-prompt event is captured.
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


OMP_JSONL_EVENT_TYPES = frozenset(
    (
        "session",
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
        "tool_execution_start",
        "tool_execution_end",
    )
)
OMP_JSONL_EVIDENCE = "omp-jsonl"

_USAGE_KEYS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cacheRead", "cache_read_tokens"),
    ("cacheWrite", "cache_write_tokens"),
)


class OmpAdapterNotConfigured(ValueError):
    """Raised when OMP execution is requested without a launcher."""


class OmpStreamJsonError(ValueError):
    """Raised when a successful OMP task lacks complete JSONL evidence."""


OMP_HEADLESS_FLAGS = ("-p", "--mode", "json", "--no-session")


@dataclass(frozen=True)
class OmpPromptRequest:
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


@dataclass(frozen=True)
class OmpTaskRequest:
    task_id: str
    task_title: str
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


OmpPromptLauncher = Callable[[OmpPromptRequest], AgentPromptResult]
OmpTaskLauncher = Callable[[OmpTaskRequest], AgentTaskResult]
OmpSubprocessRunner = Callable[[OmpPromptRequest], CommandResult]
OmpTaskSubprocessRunner = Callable[[OmpTaskRequest], CommandResult]
OmpVersionRunner = Callable[[tuple[str, ...], dict[str, str], Path], CommandResult]


class OmpAdapter:
    def __init__(
        self,
        launcher: OmpPromptLauncher | None = None,
        task_launcher: OmpTaskLauncher | None = None,
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
                transcript_path=transcript_dir / "omp-headless-prompt.json",
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
            raise OmpAdapterNotConfigured(
                "OMP headless prompt launcher is not configured"
            )
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        return self._launcher(
            OmpPromptRequest(
                prompt=prompt,
                argv=instance.command_prefix
                + instance.runtime.command
                + OMP_HEADLESS_FLAGS,
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
            raise OmpAdapterNotConfigured("OMP task launcher is not configured")
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        return self._task_launcher(
            OmpTaskRequest(
                task_id=task.id,
                task_title=task.title,
                prompt=prompt,
                argv=instance.command_prefix
                + instance.runtime.command
                + OMP_HEADLESS_FLAGS,
                env=env,
                cwd=cwd,
                transcript_path=transcript_path,
            )
        )


class SubprocessOmpPromptLauncher:
    def __init__(
        self,
        runner: OmpSubprocessRunner | None = None,
        version_runner: OmpVersionRunner | None = None,
    ) -> None:
        self._runner = runner or _run_omp_subprocess
        self._version_runner = version_runner or _run_omp_version

    def __call__(self, request: OmpPromptRequest) -> AgentPromptResult:
        result = self._runner(request)
        evidence = parse_omp_jsonl(result.stdout)
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


class SubprocessOmpTaskLauncher:
    def __init__(
        self,
        runner: OmpTaskSubprocessRunner | None = None,
        version_runner: OmpVersionRunner | None = None,
    ) -> None:
        self._runner = runner or _run_omp_task_subprocess
        self._version_runner = version_runner or _run_omp_version

    def __call__(self, request: OmpTaskRequest) -> AgentTaskResult:
        started_at = time.perf_counter()
        result = self._runner(request)
        duration_seconds = round(time.perf_counter() - started_at, 3)
        evidence = parse_omp_jsonl(result.stdout)
        harness_version = _captured_version(request, self._version_runner)
        if result.exit_code == 0 and evidence is None:
            raise OmpStreamJsonError(
                f"omp task {request.task_id} exited 0 without a complete JSONL stream"
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


def _run_omp_subprocess(request: OmpPromptRequest) -> CommandResult:
    return _run_omp_command(
        argv=request.argv, cwd=request.cwd, env=request.env, prompt=request.prompt
    )


def _run_omp_task_subprocess(request: OmpTaskRequest) -> CommandResult:
    return _run_omp_command(
        argv=request.argv, cwd=request.cwd, env=request.env, prompt=request.prompt
    )


def _run_omp_command(
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


def _run_omp_version(
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
    request: OmpPromptRequest | OmpTaskRequest, runner: OmpVersionRunner
) -> str | None:
    argv = request.argv[: -len(OMP_HEADLESS_FLAGS)] + ("--version",)
    result = runner(argv, request.env, request.cwd)
    if result.exit_code != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _write_transcript(
    *,
    request: OmpPromptRequest | OmpTaskRequest,
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
    if isinstance(request, OmpTaskRequest):
        transcript["task_id"] = request.task_id
        transcript["task_title"] = request.task_title
    if duration_seconds is not None:
        transcript["duration_seconds"] = duration_seconds
    evidence = parse_omp_jsonl(result.stdout)
    machine_evidence = _machine_evidence(evidence, harness_version)
    if machine_evidence:
        transcript["machine_evidence"] = machine_evidence
    request.transcript_path.write_text(
        json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _machine_evidence(
    evidence: dict[str, Any] | None, harness_version: str | None = None
) -> dict[str, Any]:
    machine_evidence: dict[str, Any] = {"format": OMP_JSONL_EVIDENCE}
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


def parse_omp_jsonl(output: str) -> dict[str, Any] | None:
    events = _jsonl_events(output)
    if not events or not _looks_like_omp_jsonl(events):
        return None
    if not any(event.get("type") == "agent_start" for event in events):
        return None
    if not any(event.get("type") == "agent_end" for event in events):
        return None

    message = _last_assistant_message(events)
    usage = _usage(message)
    cost = _cost(message)
    parsed: dict[str, Any] = {
        "response": _text_from_message(message),
        "usage_source": "reported" if usage else "unreported",
        "skill_stages": (),
        "tool_calls": _tool_calls(events),
        "ended": "natural",
    }
    if usage:
        parsed["usage"] = usage
    if cost is not None:
        parsed["cost"] = {"total_usd": cost}
    model = message.get("model")
    if isinstance(model, str) and model:
        parsed["model"] = model
    provider = message.get("provider")
    if isinstance(provider, str) and provider:
        parsed["provider"] = provider
    return parsed


def _looks_like_omp_jsonl(events: list[dict[str, Any]]) -> bool:
    return any(event.get("type") in OMP_JSONL_EVENT_TYPES for event in events)


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
    last: dict[str, Any] = {}
    for event in events:
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            last = message
    return last


def _text_from_message(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _usage(message: dict[str, Any]) -> dict[str, int]:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return {}
    parsed: dict[str, int] = {}
    for source, dest in _USAGE_KEYS:
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            parsed[dest] = value
    return parsed


def _cost(message: dict[str, Any]) -> float | None:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    if not isinstance(cost, dict):
        return None
    total = cost.get("total")
    if isinstance(total, int | float) and not isinstance(total, bool):
        return float(total)
    return None


def _tool_calls(events: list[dict[str, Any]]) -> tuple[str, ...]:
    names: list[str] = []
    for event in events:
        if event.get("type") != "tool_execution_end":
            continue
        name = event.get("toolName")
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(dict.fromkeys(names))
