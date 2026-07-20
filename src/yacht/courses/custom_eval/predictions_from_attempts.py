from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.artifacts import (
    candidate_patches_path,
    validate_handoff_vessel,
    write_json_artifact,
    write_jsonl_records,
)
from yacht.courses.attempts import selected_task_attempts
from yacht.courses.handoff import COURSE_HANDOFF_PATH, build_course_handoff


def write_custom_eval_predictions_from_attempts(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    validate_handoff_vessel(handoff, vessel_name)
    attempts = selected_task_attempts(
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
        comparison_name=comparison_name,
    )
    records = [_candidate_record(attempt, vessel_name) for attempt in attempts]

    write_json_artifact(logbook_dir / COURSE_HANDOFF_PATH, handoff)
    candidate_path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    write_jsonl_records(candidate_path, records)

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
