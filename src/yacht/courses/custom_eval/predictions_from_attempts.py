from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.handoff import COURSE_HANDOFF_PATH, build_course_handoff
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_task_attempt_document,
)
from yacht.courses.swe_bench.artifacts import (
    candidate_patches_path,
    validate_handoff_vessel,
)


def write_custom_eval_predictions_from_attempts(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    validate_handoff_vessel(handoff, vessel_name)
    attempts = _selected_attempts(
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
        comparison_name=comparison_name,
    )
    records = [_candidate_record(attempt, vessel_name) for attempt in attempts]

    _write_json(logbook_dir / COURSE_HANDOFF_PATH, handoff)
    candidate_path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    _write_jsonl(candidate_path, records)

    return {
        "status": "validated",
        "adapter": str(handoff["adapter"]["kind"]),
        "dataset": str(handoff["adapter"]["dataset"]),
        "split": str(handoff["adapter"]["split"]),
        "prediction_count": len(records),
        "instance_ids": [record["instance_id"] for record in records],
        "candidate_patches_path": str(candidate_path),
        "vessel": vessel_name,
    }


def _selected_attempts(
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


def _candidate_record(attempt: dict[str, Any], vessel_name: str) -> dict[str, Any]:
    response = None
    if attempt["status"] == "completed":
        response = _json_response(str(attempt["agent"]["response"]))
    return {
        "instance_id": str(attempt["task"]["id"]),
        "model_name_or_path": vessel_name,
        "response": response,
        "expect_response": _expected_response(attempt),
        "tool_calls": list(attempt["agent"]["tool_calls"]),
        "expect_tool_calls": _expected_tool_calls(attempt),
        "attempt_status": str(attempt["status"]),
    }


def _json_response(response: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _expected_response(attempt: dict[str, Any]) -> dict[str, Any]:
    task = attempt.get("task")
    if not isinstance(task, dict):
        return {"completed": True}
    expect_response = task.get("expect_response")
    if isinstance(expect_response, dict) and expect_response:
        return expect_response
    return {"completed": True}


def _expected_tool_calls(attempt: dict[str, Any]) -> list[str]:
    task = attempt.get("task")
    if not isinstance(task, dict):
        return []
    expect_tool_calls = task.get("expect_tool_calls")
    if isinstance(expect_tool_calls, list):
        return [str(tool_call) for tool_call in expect_tool_calls]
    return []


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
