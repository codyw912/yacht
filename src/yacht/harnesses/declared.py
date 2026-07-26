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
from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_harness_evidence_document,
)
from yacht.domain.model import (
    HarnessDeclaration,
    Metrics,
    RuntimeInstance,
    Task,
)
from yacht.runtimes.process import subprocess_env
from yacht.workflows.task_attempts import AgentTaskResult


EVIDENCE_PATH_ENV = "YACHT_EVIDENCE_PATH"
EVIDENCE_FILENAME = "harness-evidence.json"


class DeclaredHarnessEvidenceError(ValueError):
    """Raised when a declared harness exits 0 without valid evidence."""


@dataclass(frozen=True)
class DeclaredHarnessRequest:
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path
    evidence_path: Path
    task_id: str | None = None
    task_title: str | None = None


DeclaredSubprocessRunner = Callable[[DeclaredHarnessRequest], CommandResult]


class DeclaredHarnessAdapter:
    def __init__(
        self,
        declaration: HarnessDeclaration,
        runner: DeclaredSubprocessRunner | None = None,
    ) -> None:
        self._declaration = declaration
        self._runner = runner

    @property
    def name(self) -> str:
        return self._declaration.name

    def agent_prompt_runner(
        self,
        *,
        instance: RuntimeInstance,
        transcript_dir: Path,
    ) -> AgentPromptRunner:
        def run(prompt: str, env: dict[str, str], cwd: Path) -> AgentPromptResult:
            outcome = self._execute(
                prompt=prompt,
                instance=instance,
                env=env,
                cwd=cwd,
                transcript_path=transcript_dir / "declared-harness-prompt.json",
            )
            return AgentPromptResult(
                exit_code=outcome.exit_code,
                response=outcome.response,
                tool_calls=outcome.tool_calls,
                transcript_path=outcome.transcript_path,
            )

        return run

    def task_agent(self) -> DeclaredHarnessAdapter:
        return self

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
        outcome = self._execute(
            prompt=prompt,
            instance=instance,
            env=env,
            cwd=cwd,
            transcript_path=transcript_path,
            task_id=task.id,
            task_title=task.title,
        )
        return AgentTaskResult(
            exit_code=outcome.exit_code,
            response=outcome.response,
            tool_calls=outcome.tool_calls,
            transcript_path=outcome.transcript_path,
            metrics=Metrics(
                tokens=outcome.tokens,
                duration_seconds=outcome.duration_seconds,
                usage_source="reported" if outcome.evidence else None,
            ),
            machine_evidence=outcome.machine_evidence,
        )

    def _execute(
        self,
        *,
        prompt: str,
        instance: RuntimeInstance,
        env: dict[str, str],
        cwd: Path,
        transcript_path: Path,
        task_id: str | None = None,
        task_title: str | None = None,
    ) -> _DeclaredOutcome:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path = transcript_path.parent / EVIDENCE_FILENAME
        argv = tuple(instance.command_prefix) + tuple(instance.runtime.command)
        if self._declaration.prompt == "argument":
            argv = argv + (prompt,)
        request_env = dict(env)
        if self._declaration.evidence == "file":
            request_env[EVIDENCE_PATH_ENV] = str(evidence_path)
        request = DeclaredHarnessRequest(
            prompt=prompt,
            argv=argv,
            env=request_env,
            cwd=cwd,
            transcript_path=transcript_path,
            evidence_path=evidence_path,
            task_id=task_id,
            task_title=task_title,
        )

        started_at = time.perf_counter()
        runner = self._runner or _run_declared_subprocess(self._declaration)
        result = runner(request)
        duration_seconds = round(time.perf_counter() - started_at, 3)

        evidence = self._collect_evidence(request, result)
        response = str(evidence["response"]) if evidence else result.stdout
        tool_calls = _tool_calls_from_evidence(evidence)
        machine_evidence = (
            {"format": "yacht-harness-evidence", **evidence} if evidence else {}
        )
        _write_transcript(
            request=request,
            result=result,
            response=response,
            tool_calls=tool_calls,
            machine_evidence=machine_evidence,
            duration_seconds=duration_seconds,
        )
        return _DeclaredOutcome(
            exit_code=result.exit_code,
            response=response,
            tool_calls=tool_calls,
            transcript_path=request.transcript_path,
            tokens=_tokens_from_evidence(evidence),
            duration_seconds=duration_seconds,
            evidence=evidence,
            machine_evidence=machine_evidence,
        )

    def _collect_evidence(
        self,
        request: DeclaredHarnessRequest,
        result: CommandResult,
    ) -> dict[str, Any]:
        try:
            evidence = self._read_evidence(request, result)
        except (json.JSONDecodeError, SchemaValidationError, OSError) as error:
            if result.exit_code == 0:
                raise DeclaredHarnessEvidenceError(
                    f"declared harness {self.name} exited 0 without valid "
                    f"{EVIDENCE_FILENAME.removesuffix('.json')} evidence: {error}"
                ) from error
            return {}
        if evidence is None:
            if result.exit_code == 0:
                raise DeclaredHarnessEvidenceError(
                    f"declared harness {self.name} exited 0 without emitting "
                    "harness evidence"
                )
            return {}
        return evidence

    def _read_evidence(
        self,
        request: DeclaredHarnessRequest,
        result: CommandResult,
    ) -> dict[str, Any] | None:
        if self._declaration.evidence == "file":
            if not request.evidence_path.exists():
                return None
            payload = json.loads(request.evidence_path.read_text(encoding="utf-8"))
        else:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            if not lines:
                return None
            payload = json.loads(lines[-1])
        validate_harness_evidence_document(payload)
        return payload


@dataclass(frozen=True)
class _DeclaredOutcome:
    exit_code: int
    response: str
    tool_calls: tuple[str, ...]
    transcript_path: Path
    tokens: int
    duration_seconds: float
    evidence: dict[str, Any]
    machine_evidence: dict[str, Any]


def _run_declared_subprocess(
    declaration: HarnessDeclaration,
) -> DeclaredSubprocessRunner:
    def run(request: DeclaredHarnessRequest) -> CommandResult:
        completed = subprocess.run(
            request.argv,
            cwd=request.cwd,
            env=subprocess_env(request.argv, request.env),
            input=request.prompt if declaration.prompt == "stdin" else None,
            capture_output=True,
            check=False,
            text=True,
        )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    return run


def _write_transcript(
    *,
    request: DeclaredHarnessRequest,
    result: CommandResult,
    response: str,
    tool_calls: tuple[str, ...],
    machine_evidence: dict[str, Any],
    duration_seconds: float,
) -> None:
    transcript: dict[str, Any] = {
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
    if request.task_id is not None:
        transcript["task_id"] = request.task_id
    if request.task_title is not None:
        transcript["task_title"] = request.task_title
    if machine_evidence:
        transcript["machine_evidence"] = machine_evidence
    request.transcript_path.write_text(
        json.dumps(transcript, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _tool_calls_from_evidence(evidence: dict[str, Any]) -> tuple[str, ...]:
    tool_calls = evidence.get("tool_calls")
    if not isinstance(tool_calls, list):
        return ()
    names = []
    for entry in tool_calls:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return tuple(dict.fromkeys(names))


def _tokens_from_evidence(evidence: dict[str, Any]) -> int:
    usage = evidence.get("usage")
    if not isinstance(usage, dict):
        return 0
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens + output_tokens
    return 0


def declared_harness_adapter(declaration: HarnessDeclaration) -> DeclaredHarnessAdapter:
    return DeclaredHarnessAdapter(declaration)
