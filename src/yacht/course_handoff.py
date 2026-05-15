from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.regatta import (
    Comparison,
    ConfigError,
    CourseAdapter,
    Task,
    load_regatta,
)
from yacht.schemas import COURSE_HANDOFF_SCHEMA, validate_course_handoff_document


COURSE_HANDOFF_PATH = Path("course-handoff.json")


def build_course_handoff(config_path: Path) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    if regatta.course.adapter is None:
        raise ConfigError("course handoff requires course.adapter")
    if not regatta.comparisons:
        raise ConfigError("course handoff requires at least one comparison")

    handoff = {
        "schema": COURSE_HANDOFF_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "status": "planned",
        "adapter": _adapter_to_json(regatta.course.adapter),
        "tasks": [_task_to_json(task) for task in regatta.course.tasks],
        "comparisons": [
            _comparison_to_json(comparison) for comparison in regatta.comparisons
        ],
        "expected_outputs": _expected_outputs(regatta.course.adapter),
        "grading": _grading_to_json(regatta.course.adapter),
    }
    validate_course_handoff_document(handoff)
    return handoff


def write_course_handoff(config_path: Path, logbook_dir: Path) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    handoff_path = logbook_dir / COURSE_HANDOFF_PATH
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return handoff


def _adapter_to_json(adapter: CourseAdapter) -> dict[str, str]:
    return {
        "kind": adapter.kind,
        "dataset": adapter.dataset,
        "split": adapter.split,
        "harness": adapter.harness,
    }


def _task_to_json(task: Task) -> dict[str, str | int]:
    payload: dict[str, str | int] = {
        "id": task.id,
        "title": task.title,
        "difficulty": task.difficulty,
    }
    for key, value in (
        ("repo", task.repo),
        ("base_commit", task.base_commit),
        ("problem_statement", task.problem_statement),
    ):
        if value is not None:
            payload[key] = value
    return payload


def _comparison_to_json(comparison: Comparison) -> dict[str, Any]:
    return {
        "name": comparison.name,
        "course": comparison.course,
        "vessels": list(comparison.vessels),
    }


def _expected_outputs(adapter: CourseAdapter) -> dict[str, str]:
    return {
        "candidate_patches": f"course-handoff/{adapter.kind}/candidate-patches.jsonl",
        "grading_report": f"course-handoff/{adapter.kind}/grading-report.json",
    }


def _grading_to_json(adapter: CourseAdapter) -> dict[str, str]:
    return {
        "delegated_to": adapter.kind,
        "execution": f"{adapter.harness}-harness",
        "status": "planned",
    }
