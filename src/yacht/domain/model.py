from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from yacht.contracts.schemas import (
    SCORECARD_SCHEMA,
    WAKE_SCHEMA,
    validate_scorecard_document,
    validate_wake_document,
)
from yacht.runtimes.tool_capabilities import ToolCapability

ExpectationValue = str | bool | int | float


class ConfigError(ValueError):
    """Raised when a regatta configuration is invalid."""


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    difficulty: int
    repo: str | None = None
    repo_url: str | None = None
    base_commit: str | None = None
    problem_statement: str | None = None
    expect_response: dict[str, ExpectationValue] = field(default_factory=dict)
    expect_tool_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class CourseAdapter:
    kind: str
    dataset: str
    split: str
    harness: str
    instance_ids: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True)
class Course:
    name: str
    tasks: tuple[Task, ...]
    adapter: CourseAdapter | None = None


@dataclass(frozen=True)
class SecretReference:
    source: str
    name: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    kind: str
    required: bool = True
    command: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    prompt: str | None = None
    expect_tool_calls: tuple[str, ...] = ()
    expect_response_contains: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreflightRecipe:
    required: bool = True
    checks: tuple[PreflightCheck, ...] = ()


@dataclass(frozen=True)
class PreflightConfig:
    failure_policy: str = "abort-group"


@dataclass(frozen=True)
class ExportAttribution:
    """Who ran an eval and how they relate to what they measured.

    These are facts about the publisher, not about the run, so yacht
    cannot observe them — they are declared or the export refuses.
    """

    source_organization_name: str
    evaluator_relationship: str
    source_organization_url: str | None = None
    source_name: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_organization_name": self.source_organization_name,
            "evaluator_relationship": self.evaluator_relationship,
        }
        if self.source_organization_url is not None:
            payload["source_organization_url"] = self.source_organization_url
        if self.source_name is not None:
            payload["source_name"] = self.source_name
        return payload


@dataclass(frozen=True)
class BaselineReference:
    logbook: Path
    vessel: str


@dataclass(frozen=True)
class Comparison:
    name: str
    course: str
    vessels: tuple[str, ...]
    baseline: BaselineReference | None = None


@dataclass(frozen=True)
class RuntimeRecipe:
    name: str
    backend: str
    command: tuple[str, ...]
    harness: str | None = None
    harness_version: str | None = None
    flake: str | None = None
    image: str | None = None
    container_home: str = "/home/yacht"
    container_workspace: str = "/workspace"
    env: dict[str, str] = field(default_factory=dict)
    required_secrets: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    preflight: PreflightRecipe = field(default_factory=PreflightRecipe)
    agent: str | None = None


@dataclass(frozen=True)
class RiggingInstallResource:
    path: str
    content: str


@dataclass(frozen=True)
class RiggingInstallStep:
    method: str
    target: str
    agent: str | None = None
    runtime: str | None = None
    package: str | None = None
    source: str | None = None
    command: tuple[str, ...] = ()
    content: str | None = None
    resources: tuple[RiggingInstallResource, ...] = ()
    legacy: bool = False

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": self.method,
            "target": self.target,
        }
        if self.agent is not None:
            payload["agent"] = self.agent
        if self.runtime is not None:
            payload["runtime"] = self.runtime
        if self.package is not None:
            payload["package"] = self.package
        if self.source is not None:
            payload["source"] = self.source
        if self.command:
            payload["command"] = list(self.command)
        if self.content is not None:
            payload["content"] = self.content
        if self.resources:
            payload["resources"] = [
                {"path": resource.path, "content": resource.content}
                for resource in self.resources
            ]
        if self.legacy:
            payload["legacy"] = True
        return payload


@dataclass(frozen=True)
class RiggingRecipe:
    name: str
    tools: tuple[str, ...] = ()
    install: tuple[RiggingInstallStep, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    required_secrets: tuple[str, ...] = ()
    instructions: str = ""
    preflight: PreflightRecipe = field(default_factory=PreflightRecipe)


@dataclass(frozen=True)
class RuntimeSetupResult:
    origin: str
    origin_name: str
    action: str
    target: str
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RuntimeInstance:
    runtime: RuntimeRecipe
    temp_home: Path
    workspace_path: Path
    env: dict[str, str]
    command_prefix: tuple[str, ...]
    cleanup_paths: tuple[Path, ...]
    setup_results: tuple[RuntimeSetupResult, ...] = ()


@dataclass(frozen=True)
class Vessel:
    name: str
    model: str
    rigging: tuple[str, ...]
    runtime: str | None = None


@dataclass(frozen=True)
class Regatta:
    name: str
    course: Course
    vessels: tuple[Vessel, ...]
    preflight: PreflightConfig = field(default_factory=PreflightConfig)
    comparisons: tuple[Comparison, ...] = ()
    secrets: dict[str, SecretReference] = field(default_factory=dict)
    runtime_recipes: dict[str, RuntimeRecipe] = field(default_factory=dict)
    rigging_recipes: dict[str, RiggingRecipe] = field(default_factory=dict)
    tool_capabilities: dict[str, ToolCapability] = field(default_factory=dict)
    harness_declarations: dict[str, HarnessDeclaration] = field(default_factory=dict)
    export: ExportAttribution | None = None


@dataclass(frozen=True)
class HarnessDeclaration:
    name: str
    prompt: str = "argument"
    evidence: str = "stdout"
    command: tuple[str, ...] = ()
    install: HarnessInstall | None = None
    evidence_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessInstall:
    sha256: str
    url: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class Metrics:
    tokens: int
    duration_seconds: float
    usage_source: str | None = None

    def to_json(self) -> dict[str, int | float | str]:
        payload: dict[str, int | float | str] = {
            "tokens": self.tokens,
            "duration_seconds": self.duration_seconds,
        }
        if self.usage_source is not None:
            payload["usage_source"] = self.usage_source
        return payload


@dataclass(frozen=True)
class Wake:
    regatta: str
    course: str
    vessel: str
    model: str
    rigging: tuple[str, ...]
    task_id: str
    task_title: str
    passed: bool
    metrics: Metrics

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": WAKE_SCHEMA,
            "regatta": self.regatta,
            "course": self.course,
            "vessel": self.vessel,
            "model": self.model,
            "rigging": list(self.rigging),
            "task_id": self.task_id,
            "task_title": self.task_title,
            "passed": self.passed,
            "metrics": self.metrics.to_json(),
        }


@dataclass(frozen=True)
class VesselScore:
    name: str
    model: str
    rigging: tuple[str, ...]
    tasks_total: int
    tasks_passed: int
    success_rate: float
    total_tokens: int
    total_duration_seconds: float

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "rigging": list(self.rigging),
            "tasks_total": self.tasks_total,
            "tasks_passed": self.tasks_passed,
            "success_rate": self.success_rate,
            "total_tokens": self.total_tokens,
            "total_duration_seconds": self.total_duration_seconds,
        }


@dataclass(frozen=True)
class Scorecard:
    regatta: str
    course: str
    vessels: tuple[VesselScore, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SCORECARD_SCHEMA,
            "regatta": self.regatta,
            "course": self.course,
            "vessels": [vessel.to_json() for vessel in self.vessels],
        }


class TaskRunner(Protocol):
    def run_task(
        self, regatta: str, course: str, vessel: Vessel, task: Task
    ) -> Wake: ...


class MockTaskRunner:
    def run_task(self, regatta: str, course: str, vessel: Vessel, task: Task) -> Wake:
        token_multiplier = 0.82 if "memory" in vessel.rigging else 1.0
        duration_multiplier = 1.12 if "memory" in vessel.rigging else 1.0
        base_tokens = 600 + (task.difficulty * 250)
        base_duration = 8.0 + (task.difficulty * 3.5)

        return Wake(
            regatta=regatta,
            course=course,
            vessel=vessel.name,
            model=vessel.model,
            rigging=vessel.rigging,
            task_id=task.id,
            task_title=task.title,
            passed=True,
            metrics=Metrics(
                tokens=round(base_tokens * token_multiplier),
                duration_seconds=round(base_duration * duration_multiplier, 2),
            ),
        )


def run_regatta(
    config_path: Path,
    logbook_dir: Path,
    runner: TaskRunner | None = None,
) -> dict[str, Any]:
    from yacht.config.loader import load_regatta

    regatta = load_regatta(config_path)
    task_runner = runner or MockTaskRunner()
    wake_dir = logbook_dir / "wake"
    wake_dir.mkdir(parents=True, exist_ok=True)

    vessel_results = []
    for vessel in regatta.vessels:
        wakes = [
            task_runner.run_task(regatta.name, regatta.course.name, vessel, task)
            for task in regatta.course.tasks
        ]
        for wake in wakes:
            wake_path = wake_dir / f"{wake.vessel}__{wake.task_id}.json"
            _write_json(wake_path, wake.to_json())

        vessel_results.append(_summarize_vessel(vessel, wakes))

    scorecard = Scorecard(
        regatta=regatta.name,
        course=regatta.course.name,
        vessels=tuple(vessel_results),
    )
    scorecard_json = scorecard.to_json()
    validate_scorecard_document(scorecard_json)
    _write_json(logbook_dir / "scorecard.json", scorecard_json)
    return scorecard_json


def load_regatta(config_path: Path) -> Regatta:
    from yacht.config.loader import load_regatta as load

    return load(config_path)


def _summarize_vessel(vessel: Vessel, wakes: list[Wake]) -> VesselScore:
    tasks_total = len(wakes)
    tasks_passed = sum(1 for wake in wakes if wake.passed)
    total_tokens = sum(wake.metrics.tokens for wake in wakes)
    total_duration = sum(wake.metrics.duration_seconds for wake in wakes)

    return VesselScore(
        name=vessel.name,
        model=vessel.model,
        rigging=vessel.rigging,
        tasks_total=tasks_total,
        tasks_passed=tasks_passed,
        success_rate=tasks_passed / tasks_total if tasks_total else 0,
        total_tokens=total_tokens,
        total_duration_seconds=round(total_duration, 2),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if payload.get("schema") == WAKE_SCHEMA:
        validate_wake_document(payload)
    if payload.get("schema") == SCORECARD_SCHEMA:
        validate_scorecard_document(payload)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
