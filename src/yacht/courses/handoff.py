from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.config.loader import load_regatta
from yacht.courses.registry import course_adapter
from yacht.courses.registry import course_adapter_to_json
from yacht.courses.registry import evaluator_adapter
from yacht.logbook.io import write_json
from yacht.domain.model import (
    Comparison,
    ConfigError,
    CourseAdapter,
    Task,
)
from yacht.contracts.schemas import (
    COURSE_HANDOFF_SCHEMA,
    validate_course_handoff_document,
)


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
    if regatta.export is not None:
        handoff["export"] = regatta.export.to_json()
    validate_course_handoff_document(handoff)
    return handoff


def write_course_handoff(config_path: Path, logbook_dir: Path) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    write_json(logbook_dir / COURSE_HANDOFF_PATH, handoff)
    return handoff


def _adapter_to_json(adapter: CourseAdapter) -> dict[str, Any]:
    payload = course_adapter_to_json(adapter)
    if adapter.kind == "custom-eval":
        from yacht.courses.task_directory import task_directory_digest

        payload["content_digest"] = task_directory_digest(Path(adapter.dataset))
    return payload


def _task_to_json(task: Task) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    if task.expect_response:
        payload["expect_response"] = dict(task.expect_response)
    if task.expect_tool_calls:
        payload["expect_tool_calls"] = list(task.expect_tool_calls)
    return payload


def _comparison_to_json(comparison: Comparison) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": comparison.name,
        "course": comparison.course,
        "vessels": list(comparison.vessels),
    }
    if comparison.baseline is not None:
        payload["baseline"] = {
            "logbook": str(comparison.baseline.logbook),
            "vessel": comparison.baseline.vessel,
        }
    return payload


def _expected_outputs(adapter: CourseAdapter) -> dict[str, str]:
    return course_adapter(adapter.kind).expected_outputs()


def _grading_to_json(adapter: CourseAdapter) -> dict[str, str]:
    return evaluator_adapter(adapter.kind).grading(adapter.harness)
