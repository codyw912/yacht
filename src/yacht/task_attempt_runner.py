from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.benchmark_adapters import benchmark_adapter
from yacht.harness_adapters import TaskAgent
from yacht.harness_adapters import supported_task_attempt_names
from yacht.harness_adapters import task_agent as harness_task_agent
from yacht.regatta import (
    Comparison,
    ConfigError,
    Regatta,
    RuntimeRecipe,
    Task,
    Vessel,
    load_regatta,
)
from yacht.runtime_backend import RuntimePreparationError, runtime_backend_for_recipe
from yacht.task_attempts import write_task_attempt


TASK_ATTEMPT_AGENTS = frozenset(supported_task_attempt_names())


def run_task_attempts(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_name: str,
    task_agent: TaskAgent | None = None,
) -> dict[str, Any]:
    if agent_name not in TASK_ATTEMPT_AGENTS:
        raise ConfigError(f"unsupported task attempt agent {agent_name}")

    regatta = load_regatta(config_path)
    if not regatta.comparisons:
        raise ConfigError("task attempts require at least one comparison")

    agent = task_agent or harness_task_agent(agent_name)
    attempts = [
        attempt
        for comparison in regatta.comparisons
        for attempt in _run_comparison_task_attempts(
            regatta=regatta,
            comparison=comparison,
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent=agent,
        )
    ]
    status = (
        "failed"
        if any(attempt["status"] != "completed" for attempt in attempts)
        else "completed"
    )
    return {
        "status": status,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "agent": agent_name,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


def _run_comparison_task_attempts(
    *,
    regatta: Regatta,
    comparison: Comparison,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent: TaskAgent,
) -> list[dict[str, str]]:
    return [
        _run_vessel_task_attempt(
            regatta=regatta,
            comparison=comparison,
            vessel=_vessel_by_name(regatta, vessel_name),
            task=task,
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent=agent,
        )
        for vessel_name in comparison.vessels
        for task in regatta.course.tasks
    ]


def _run_vessel_task_attempt(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent: TaskAgent,
) -> dict[str, str]:
    task = _task_for_attempt(regatta, task)
    attempt_workspace_path = _workspace_for_attempt(
        regatta=regatta,
        comparison=comparison,
        vessel=vessel,
        task=task,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
    )
    try:
        runtime = _runtime_for_vessel(regatta, vessel)
        instance = runtime_backend_for_recipe(runtime).prepare(
            regatta=regatta,
            vessel=vessel,
            trial_root=logbook_dir / "runtime" / comparison.name,
            workspace_path=attempt_workspace_path,
            secret_values=secret_values,
        )
    except RuntimePreparationError as error:
        raise ConfigError(str(error)) from error

    prompt = _task_prompt(regatta, vessel, task)
    artifact_path = _task_attempt_path(logbook_dir, comparison, vessel, task)
    transcript_path = _task_transcript_path(logbook_dir, comparison, vessel, task)
    result = agent.run_task(
        instance=instance,
        task=task,
        prompt=prompt,
        env=instance.env,
        cwd=instance.workspace_path,
        transcript_path=transcript_path,
    )
    artifact = write_task_attempt(
        artifact_path=artifact_path,
        regatta=regatta,
        comparison=comparison,
        vessel=vessel,
        task=task,
        instance=instance,
        prompt=prompt,
        result=result,
    )
    return {
        "comparison": comparison.name,
        "vessel": vessel.name,
        "task_id": task.id,
        "status": str(artifact["status"]),
        "artifact_path": str(artifact_path),
        "transcript_path": str(transcript_path),
    }


def _task_prompt(regatta: Regatta, vessel: Vessel, task: Task) -> str:
    prompt = f"Task ID: {task.id}\nTitle: {task.title}\n"
    if regatta.course.adapter is not None:
        prompt += benchmark_adapter(
            regatta.course.adapter.kind
        ).task_prompt_instructions(task)
    instructions = _rigging_instructions(regatta, vessel)
    if instructions:
        prompt += "\nRigging instructions:\n"
        prompt += "".join(f"- {instruction}\n" for instruction in instructions)
    return prompt


def _task_for_attempt(regatta: Regatta, task: Task) -> Task:
    if regatta.course.adapter is None:
        return task
    return benchmark_adapter(regatta.course.adapter.kind).task_with_context(
        task=task,
        adapter=regatta.course.adapter,
    )


def _workspace_for_attempt(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
    logbook_dir: Path,
    workspace_path: Path,
) -> Path:
    if regatta.course.adapter is None:
        return workspace_path
    return benchmark_adapter(regatta.course.adapter.kind).workspace_for_attempt(
        task=task,
        workspace_path=workspace_path,
        workspace_root=logbook_dir / f"{regatta.course.adapter.kind}-workspaces",
        comparison_name=comparison.name,
        vessel_name=vessel.name,
    )


def _rigging_instructions(regatta: Regatta, vessel: Vessel) -> tuple[str, ...]:
    return tuple(
        instruction
        for rigging_name in vessel.rigging
        if (instruction := regatta.rigging_recipes[rigging_name].instructions)
    )


def _task_attempt_path(
    logbook_dir: Path,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
) -> Path:
    return (
        logbook_dir
        / "task-attempts"
        / comparison.name
        / vessel.name
        / f"{task.id}.json"
    )


def _task_transcript_path(
    logbook_dir: Path,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
) -> Path:
    return (
        logbook_dir
        / "transcripts"
        / comparison.name
        / vessel.name
        / "tasks"
        / f"{task.id}.json"
    )


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison references undefined vessel {name}")


def _runtime_for_vessel(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(f"vessel {vessel.name} does not define a runtime")
    return regatta.runtime_recipes[vessel.runtime]
