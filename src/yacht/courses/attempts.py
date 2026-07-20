from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_task_attempt_document,
)
from yacht.domain.model import ConfigError


def selected_task_attempts(
    *,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None,
) -> list[dict[str, Any]]:
    attempts = [
        attempt
        for attempt in _load_task_attempts(logbook_dir)
        if attempt["vessel"] == vessel_name
        and (comparison_name is None or attempt["comparison"] == comparison_name)
    ]
    if not attempts:
        raise ConfigError(f"task attempt artifacts not found for vessel {vessel_name}")

    comparison_names = {str(attempt["comparison"]) for attempt in attempts}
    if comparison_name is None and len(comparison_names) > 1:
        raise ConfigError(
            f"vessel {vessel_name} has task attempts in multiple comparisons; "
            "pass --comparison"
        )
    return sorted(attempts, key=lambda attempt: str(attempt["task"]["id"]))


def _load_task_attempts(logbook_dir: Path) -> list[dict[str, Any]]:
    attempts_root = logbook_dir / "task-attempts"
    paths = sorted(attempts_root.glob("*/*/*.json"))
    if not paths:
        raise ConfigError(f"task attempt artifacts not found: {attempts_root}")
    return [_load_task_attempt(path) for path in paths]


def _load_task_attempt(path: Path) -> dict[str, Any]:
    try:
        attempt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"task attempt artifact is not valid JSON: {error}"
        ) from error
    if not isinstance(attempt, dict):
        raise ConfigError("task attempt artifact must be a JSON object")
    try:
        validate_task_attempt_document(attempt)
    except SchemaValidationError as error:
        raise ConfigError(f"task attempt artifact is invalid: {error}") from error
    return attempt
