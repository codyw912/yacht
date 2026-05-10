from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from yacht.schemas import (
    SCORECARD_SCHEMA,
    WAKE_SCHEMA,
    SchemaValidationError,
    validate_regatta_document,
    validate_scorecard_document,
    validate_wake_document,
)


class ConfigError(ValueError):
    """Raised when a regatta configuration is invalid."""


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    difficulty: int


@dataclass(frozen=True)
class CourseAdapter:
    kind: str
    dataset: str
    split: str
    harness: str


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


@dataclass(frozen=True)
class PreflightRecipe:
    required: bool = True
    checks: tuple[PreflightCheck, ...] = ()


@dataclass(frozen=True)
class PreflightConfig:
    failure_policy: str = "abort-group"


@dataclass(frozen=True)
class Comparison:
    name: str
    course: str
    vessels: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeRecipe:
    name: str
    backend: str
    flake: str
    command: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)
    required_secrets: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    preflight: PreflightRecipe = field(default_factory=PreflightRecipe)


@dataclass(frozen=True)
class RiggingRecipe:
    name: str
    install: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    required_secrets: tuple[str, ...] = ()
    instructions: str = ""
    preflight: PreflightRecipe = field(default_factory=PreflightRecipe)


@dataclass(frozen=True)
class RuntimeInstance:
    runtime: RuntimeRecipe
    temp_home: Path
    workspace_path: Path
    env: dict[str, str]
    command_prefix: tuple[str, ...]
    cleanup_paths: tuple[Path, ...]


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


@dataclass(frozen=True)
class Metrics:
    tokens: int
    duration_seconds: float

    def to_json(self) -> dict[str, int | float]:
        return {
            "tokens": self.tokens,
            "duration_seconds": self.duration_seconds,
        }


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
    def run_task(self, regatta: str, course: str, vessel: Vessel, task: Task) -> Wake:
        ...


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
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    try:
        validate_regatta_document(raw)
    except SchemaValidationError as error:
        raise ConfigError(str(error)) from error

    course = Course(
        name=str(raw["course"]["name"]),
        tasks=tuple(
            Task(
                id=str(task["id"]),
                title=str(task["title"]),
                difficulty=int(task.get("difficulty", 1)),
            )
            for task in raw["course"]["tasks"]
        ),
        adapter=_parse_course_adapter(raw["course"]),
    )
    vessels = tuple(
        Vessel(
            name=str(vessel["name"]),
            model=str(vessel["model"]),
            rigging=tuple(str(item) for item in vessel.get("rigging", ())),
            runtime=str(vessel["runtime"]) if "runtime" in vessel else None,
        )
        for vessel in raw["vessels"]
    )
    return Regatta(
        name=str(raw["regatta"]["name"]),
        course=course,
        vessels=vessels,
        preflight=_parse_preflight_config(raw),
        comparisons=_parse_comparisons(raw, course.name),
        secrets=_parse_secrets(raw),
        runtime_recipes=_parse_runtime_recipes(raw),
        rigging_recipes=_parse_rigging_recipes(raw),
    )


def _parse_preflight_config(raw: dict[str, Any]) -> PreflightConfig:
    preflight = raw.get("preflight", {})
    return PreflightConfig(
        failure_policy=str(preflight.get("failure_policy", "abort-group")),
    )


def _parse_course_adapter(raw_course: dict[str, Any]) -> CourseAdapter | None:
    if "adapter" not in raw_course:
        return None

    adapter = raw_course["adapter"]
    return CourseAdapter(
        kind=str(adapter["kind"]),
        dataset=str(adapter["dataset"]),
        split=str(adapter["split"]),
        harness=str(adapter["harness"]),
    )


def _parse_comparisons(raw: dict[str, Any], course_name: str) -> tuple[Comparison, ...]:
    return tuple(
        Comparison(
            name=str(comparison["name"]),
            course=str(comparison.get("course", course_name)),
            vessels=tuple(str(item) for item in comparison["vessels"]),
        )
        for comparison in raw.get("comparisons", ())
    )


def _parse_secrets(raw: dict[str, Any]) -> dict[str, SecretReference]:
    return {
        str(name): SecretReference(
            source=str(secret["source"]),
            name=str(secret["name"]) if "name" in secret else None,
            path=str(secret["path"]) if "path" in secret else None,
        )
        for name, secret in raw.get("secrets", {}).items()
    }


def _parse_runtime_recipes(raw: dict[str, Any]) -> dict[str, RuntimeRecipe]:
    return {
        str(name): RuntimeRecipe(
            name=str(name),
            backend=str(runtime["backend"]),
            flake=str(runtime["flake"]),
            command=tuple(str(item) for item in runtime["command"]),
            env={
                str(key): str(value)
                for key, value in runtime.get("env", {}).items()
            },
            required_secrets=tuple(
                str(item) for item in runtime.get("required_secrets", ())
            ),
            mounts=tuple(str(item) for item in runtime.get("mounts", ())),
            preflight=_parse_preflight_recipe(runtime.get("preflight", {})),
        )
        for name, runtime in raw.get("runtimes", {}).items()
    }


def _parse_rigging_recipes(raw: dict[str, Any]) -> dict[str, RiggingRecipe]:
    return {
        str(name): RiggingRecipe(
            name=str(name),
            install=tuple(str(item) for item in rigging.get("install", ())),
            env={
                str(key): str(value)
                for key, value in rigging.get("env", {}).items()
            },
            required_secrets=tuple(
                str(item) for item in rigging.get("required_secrets", ())
            ),
            instructions=str(rigging.get("instructions", "")),
            preflight=_parse_preflight_recipe(rigging.get("preflight", {})),
        )
        for name, rigging in raw.get("riggings", {}).items()
    }


def _parse_preflight_recipe(raw: dict[str, Any]) -> PreflightRecipe:
    return PreflightRecipe(
        required=bool(raw.get("required", True)),
        checks=tuple(_parse_preflight_check(check) for check in raw.get("checks", ())),
    )


def _parse_preflight_check(raw: dict[str, Any]) -> PreflightCheck:
    return PreflightCheck(
        name=str(raw["name"]),
        kind=str(raw["kind"]),
        required=bool(raw.get("required", True)),
        command=tuple(str(item) for item in raw.get("command", ())),
        env=tuple(str(item) for item in raw.get("env", ())),
        prompt=str(raw["prompt"]) if "prompt" in raw else None,
        expect_tool_calls=tuple(str(item) for item in raw.get("expect_tool_calls", ())),
    )


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
