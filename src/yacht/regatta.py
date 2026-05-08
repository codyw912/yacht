from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
class Course:
    name: str
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Vessel:
    name: str
    model: str
    rigging: tuple[str, ...]


@dataclass(frozen=True)
class Regatta:
    name: str
    course: Course
    vessels: tuple[Vessel, ...]


def run_regatta(config_path: Path, logbook_dir: Path) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    wake_dir = logbook_dir / "wake"
    wake_dir.mkdir(parents=True, exist_ok=True)

    vessel_results = []
    for vessel in regatta.vessels:
        wakes = [_run_task(regatta, vessel, task) for task in regatta.course.tasks]
        for wake in wakes:
            wake_path = wake_dir / f"{wake['vessel']}__{wake['task_id']}.json"
            _write_json(wake_path, wake)

        vessel_results.append(_summarize_vessel(vessel, wakes))

    scorecard = {
        "schema": SCORECARD_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "vessels": vessel_results,
    }
    validate_scorecard_document(scorecard)
    _write_json(logbook_dir / "scorecard.json", scorecard)
    return scorecard


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
    )
    vessels = tuple(
        Vessel(
            name=str(vessel["name"]),
            model=str(vessel["model"]),
            rigging=tuple(str(item) for item in vessel.get("rigging", ())),
        )
        for vessel in raw["vessels"]
    )
    return Regatta(name=str(raw["regatta"]["name"]), course=course, vessels=vessels)


def _run_task(regatta: Regatta, vessel: Vessel, task: Task) -> dict[str, Any]:
    token_multiplier = 0.82 if "memory" in vessel.rigging else 1.0
    duration_multiplier = 1.12 if "memory" in vessel.rigging else 1.0
    base_tokens = 600 + (task.difficulty * 250)
    base_duration = 8.0 + (task.difficulty * 3.5)

    return {
        "schema": WAKE_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "vessel": vessel.name,
        "model": vessel.model,
        "rigging": list(vessel.rigging),
        "task_id": task.id,
        "task_title": task.title,
        "passed": True,
        "metrics": {
            "tokens": round(base_tokens * token_multiplier),
            "duration_seconds": round(base_duration * duration_multiplier, 2),
        },
    }


def _summarize_vessel(vessel: Vessel, wakes: list[dict[str, Any]]) -> dict[str, Any]:
    tasks_total = len(wakes)
    tasks_passed = sum(1 for wake in wakes if wake["passed"])
    total_tokens = sum(int(wake["metrics"]["tokens"]) for wake in wakes)
    total_duration = sum(float(wake["metrics"]["duration_seconds"]) for wake in wakes)

    return {
        "name": vessel.name,
        "model": vessel.model,
        "rigging": list(vessel.rigging),
        "tasks_total": tasks_total,
        "tasks_passed": tasks_passed,
        "success_rate": tasks_passed / tasks_total if tasks_total else 0,
        "total_tokens": total_tokens,
        "total_duration_seconds": round(total_duration, 2),
    }


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
