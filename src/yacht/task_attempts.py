from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yacht.regatta import (
    Comparison,
    Metrics,
    Regatta,
    RuntimeInstance,
    SecretReference,
    Task,
    Vessel,
)
from yacht.schemas import TASK_ATTEMPT_SCHEMA, validate_task_attempt_document


@dataclass(frozen=True)
class AgentTaskResult:
    exit_code: int
    response: str
    tool_calls: tuple[str, ...]
    transcript_path: Path
    metrics: Metrics
    machine_evidence: dict[str, Any] = field(default_factory=dict)


def write_task_attempt(
    *,
    artifact_path: Path,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
    instance: RuntimeInstance,
    prompt: str,
    result: AgentTaskResult,
) -> dict[str, Any]:
    artifact = build_task_attempt(
        regatta=regatta,
        comparison=comparison,
        vessel=vessel,
        task=task,
        instance=instance,
        prompt=prompt,
        result=result,
    )
    validate_task_attempt_document(artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def build_task_attempt(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
    instance: RuntimeInstance,
    prompt: str,
    result: AgentTaskResult,
) -> dict[str, Any]:
    return {
        "schema": TASK_ATTEMPT_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "comparison": comparison.name,
        "vessel": vessel.name,
        "model": vessel.model,
        "rigging": list(vessel.rigging),
        "runtime": instance.runtime.name,
        "status": _status_for_exit_code(result.exit_code),
        "task": _task_to_json(task),
        "runtime_context": _runtime_context_to_json(instance),
        "prompt": prompt,
        "agent": _agent_to_json(result),
        "metrics": result.metrics.to_json(),
        "secret_refs": _secret_refs_to_json(
            regatta,
            _required_secret_names(regatta, vessel, instance),
        ),
    }


def _status_for_exit_code(exit_code: int) -> str:
    return "completed" if exit_code == 0 else "failed"


def _task_to_json(task: Task) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": task.id,
        "title": task.title,
        "difficulty": task.difficulty,
    }
    for key, value in (
        ("repo", task.repo),
        ("repo_url", task.repo_url),
        ("base_commit", task.base_commit),
        ("problem_statement", task.problem_statement),
    ):
        if value is not None:
            payload[key] = value
    if task.expect_response:
        payload["expect_response"] = dict(task.expect_response)
    return payload


def _runtime_context_to_json(instance: RuntimeInstance) -> dict[str, Any]:
    return {
        "backend": instance.runtime.backend,
        "harness": _runtime_harness(instance),
        "agent": _runtime_harness(instance),
        "temp_home": str(instance.temp_home),
        "workspace_path": str(instance.workspace_path),
        "command_prefix": list(instance.command_prefix),
        "command": list(instance.runtime.command),
        "cleanup_paths": [str(path) for path in instance.cleanup_paths],
    }


def _runtime_harness(instance: RuntimeInstance) -> str | None:
    if instance.runtime.harness is not None:
        return instance.runtime.harness
    if instance.runtime.agent is not None:
        return instance.runtime.agent
    if instance.runtime.command:
        return instance.runtime.command[0]
    return None


def _agent_to_json(result: AgentTaskResult) -> dict[str, Any]:
    agent = {
        "exit_code": result.exit_code,
        "response": result.response,
        "tool_calls": list(result.tool_calls),
        "transcript_path": str(result.transcript_path),
    }
    if result.machine_evidence:
        agent["machine_evidence"] = result.machine_evidence
    return agent


def _secret_refs_to_json(
    regatta: Regatta,
    required_secret_names: tuple[str, ...],
) -> list[dict[str, object]]:
    return [
        _secret_ref_to_json(name, regatta.secrets[name])
        for name in required_secret_names
    ]


def _required_secret_names(
    regatta: Regatta,
    vessel: Vessel,
    instance: RuntimeInstance,
) -> tuple[str, ...]:
    names = list(instance.runtime.required_secrets)
    for rigging_name in vessel.rigging:
        names.extend(regatta.rigging_recipes[rigging_name].required_secrets)
    return tuple(dict.fromkeys(names))


def _secret_ref_to_json(name: str, secret: SecretReference) -> dict[str, object]:
    return {
        "name": name,
        "source": secret.source,
        "ref": _secret_ref_label(secret),
        "redacted": True,
    }


def _secret_ref_label(secret: SecretReference) -> str:
    if secret.source == "env" and secret.name is not None:
        return secret.name
    if secret.source == "file" and secret.path is not None:
        return secret.path
    return secret.source
