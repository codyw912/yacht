from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.config.loader import load_regatta
from yacht.courses.artifacts import (
    candidate_patches_path,
    validate_handoff_vessel,
    vessel_artifact_dir,
    write_json_artifact,
    write_jsonl_records,
)
from yacht.courses.attempts import selected_task_attempts
from yacht.courses.handoff import COURSE_HANDOFF_PATH, build_course_handoff
from yacht.courses.livecodebench.task_context import window_question_ids
from yacht.domain.model import ConfigError
from yacht.preflight.execution import parse_agent_response_json


LCB_WINDOW_FILENAME = "lcb-window.json"


def write_livecodebench_predictions_from_attempts(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    validate_handoff_vessel(handoff, vessel_name)
    regatta = load_regatta(config_path)
    if regatta.course.adapter is None:
        raise ConfigError("livecodebench predictions require course.adapter")
    attempts = selected_task_attempts(
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
        comparison_name=comparison_name,
    )
    records = [_candidate_record(attempt, vessel_name) for attempt in attempts]
    window_ids = window_question_ids(regatta.course.adapter)
    outside = sorted({record["instance_id"] for record in records} - set(window_ids))
    if outside:
        raise ConfigError(
            "task attempts contain questions outside the configured "
            "contest-date window: " + ", ".join(outside)
        )

    write_json_artifact(logbook_dir / COURSE_HANDOFF_PATH, handoff)
    candidate_path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    write_jsonl_records(candidate_path, records)
    window_path = (
        vessel_artifact_dir(
            logbook_dir=logbook_dir,
            handoff=handoff,
            vessel_name=vessel_name,
        )
        / LCB_WINDOW_FILENAME
    )
    window_path.parent.mkdir(parents=True, exist_ok=True)
    window_path.write_text(
        json.dumps(window_ids, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "validated",
        "adapter": str(handoff["adapter"]["kind"]),
        "dataset": str(handoff["adapter"]["dataset"]),
        "split": str(handoff["adapter"]["split"]),
        "prediction_count": len(records),
        "instance_ids": [record["instance_id"] for record in records],
        "candidate_patches_path": str(candidate_path),
        "window_path": str(window_path),
        "window_instances": len(window_ids),
        "vessel": vessel_name,
    }


def _candidate_record(attempt: dict[str, Any], vessel_name: str) -> dict[str, str]:
    if attempt["status"] != "completed":
        raise ConfigError(
            "task attempt "
            f"{attempt['comparison']}/{vessel_name}/{attempt['task']['id']} "
            "is not completed"
        )
    return {
        "instance_id": str(attempt["task"]["id"]),
        "model_name_or_path": vessel_name,
        "code": _code_from_response(str(attempt["agent"]["response"]), attempt),
    }


def _code_from_response(response: str, attempt: dict[str, Any]) -> str:
    payload = parse_agent_response_json(response)
    if isinstance(payload, dict):
        code = payload.get("code")
        if isinstance(code, str) and code.strip():
            return code
    raise ConfigError(
        "task attempt "
        f"{attempt['comparison']}/{attempt['vessel']}/{attempt['task']['id']} "
        "response must be a JSON object with a non-empty code string"
    )
