from __future__ import annotations

from typing import Any


REGATTA_SCHEMA = "yacht.regatta.v1"
WAKE_SCHEMA = "yacht.wake.v1"
SCORECARD_SCHEMA = "yacht.scorecard.v1"


class SchemaValidationError(ValueError):
    """Raised when a YACHT document does not match its contract."""


def validate_regatta_document(document: dict[str, Any]) -> None:
    _require_object(document, "regatta document")
    _require_keys(document, ("regatta", "course", "vessels"), "regatta document")

    regatta = _require_object(document["regatta"], "regatta")
    _require_non_empty_string(regatta.get("name"), "regatta.name")

    course = _require_object(document["course"], "course")
    _require_non_empty_string(course.get("name"), "course.name")
    tasks = _require_list(course.get("tasks"), "course.tasks")
    if not tasks:
        raise SchemaValidationError("course.tasks must contain at least one task")
    for index, task_value in enumerate(tasks):
        task = _require_object(task_value, f"course.tasks[{index}]")
        _require_non_empty_string(task.get("id"), f"course.tasks[{index}].id")
        _require_non_empty_string(task.get("title"), f"course.tasks[{index}].title")
        difficulty = task.get("difficulty", 1)
        if not isinstance(difficulty, int) or difficulty < 1:
            raise SchemaValidationError(
                f"course.tasks[{index}].difficulty must be an integer >= 1"
            )

    vessels = _require_list(document["vessels"], "vessels")
    if not vessels:
        raise SchemaValidationError("vessels must contain at least one vessel")
    for index, vessel_value in enumerate(vessels):
        vessel = _require_object(vessel_value, f"vessels[{index}]")
        _require_non_empty_string(vessel.get("name"), f"vessels[{index}].name")
        _require_non_empty_string(vessel.get("model"), f"vessels[{index}].model")
        rigging = vessel.get("rigging", [])
        if not isinstance(rigging, list) or not all(
            isinstance(item, str) for item in rigging
        ):
            raise SchemaValidationError(
                f"vessels[{index}].rigging must be a list of strings"
            )


def validate_wake_document(document: dict[str, Any]) -> None:
    _require_object(document, "wake")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "vessel",
            "model",
            "rigging",
            "task_id",
            "task_title",
            "passed",
            "metrics",
        ),
        "wake",
    )
    _require_schema(document, WAKE_SCHEMA, "wake")
    for key in ("regatta", "course", "vessel", "model", "task_id", "task_title"):
        _require_non_empty_string(document[key], key)
    _require_string_list(document["rigging"], "rigging")
    if not isinstance(document["passed"], bool):
        raise SchemaValidationError("passed must be a boolean")

    metrics = _require_object(document["metrics"], "metrics")
    if not isinstance(metrics.get("tokens"), int) or metrics["tokens"] < 0:
        raise SchemaValidationError("metrics.tokens must be an integer >= 0")
    if (
        not isinstance(metrics.get("duration_seconds"), int | float)
        or metrics["duration_seconds"] < 0
    ):
        raise SchemaValidationError("metrics.duration_seconds must be a number >= 0")


def validate_scorecard_document(document: dict[str, Any]) -> None:
    _require_object(document, "scorecard")
    _require_keys(document, ("schema", "regatta", "course", "vessels"), "scorecard")
    _require_schema(document, SCORECARD_SCHEMA, "scorecard")
    _require_non_empty_string(document["regatta"], "regatta")
    _require_non_empty_string(document["course"], "course")

    vessels = _require_list(document["vessels"], "vessels")
    if not vessels:
        raise SchemaValidationError("vessels must contain at least one vessel")
    for index, vessel_value in enumerate(vessels):
        vessel = _require_object(vessel_value, f"vessels[{index}]")
        _require_non_empty_string(vessel.get("name"), f"vessels[{index}].name")
        _require_non_empty_string(vessel.get("model"), f"vessels[{index}].model")
        _require_string_list(vessel.get("rigging"), f"vessels[{index}].rigging")
        for key in ("tasks_total", "tasks_passed", "total_tokens"):
            value = vessel.get(key)
            if not isinstance(value, int) or value < 0:
                raise SchemaValidationError(
                    f"vessels[{index}].{key} must be an integer >= 0"
                )
        for key in ("success_rate", "total_duration_seconds"):
            value = vessel.get(key)
            if not isinstance(value, int | float) or value < 0:
                raise SchemaValidationError(
                    f"vessels[{index}].{key} must be a number >= 0"
                )


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{path} must be an object")
    return value


def _require_keys(document: dict[str, Any], keys: tuple[str, ...], path: str) -> None:
    for key in keys:
        if key not in document:
            raise SchemaValidationError(f"{path}.{key} is required")


def _require_non_empty_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise SchemaValidationError(f"{path} must be a non-empty string")


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaValidationError(f"{path} must be a list")
    return value


def _require_string_list(value: Any, path: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaValidationError(f"{path} must be a list of strings")


def _require_schema(document: dict[str, Any], expected: str, path: str) -> None:
    if document.get("schema") != expected:
        raise SchemaValidationError(f"{path}.schema must be {expected}")
