from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.course_handoff import COURSE_HANDOFF_PATH, build_course_handoff
from yacht.regatta import ConfigError


SWE_BENCH_PREDICTION_FIELDS = (
    "instance_id",
    "model_name_or_path",
    "model_patch",
)


def write_swe_bench_predictions(
    *,
    config_path: Path,
    predictions_path: Path,
    logbook_dir: Path,
) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    records = _load_prediction_records(predictions_path)
    _validate_prediction_records(
        records,
        allowed_instance_ids=_task_ids(handoff),
    )

    _write_json(logbook_dir / COURSE_HANDOFF_PATH, handoff)
    candidate_path = logbook_dir / str(handoff["expected_outputs"]["candidate_patches"])
    _write_jsonl(candidate_path, records)

    return {
        "status": "validated",
        "adapter": str(handoff["adapter"]["kind"]),
        "dataset": str(handoff["adapter"]["dataset"]),
        "split": str(handoff["adapter"]["split"]),
        "prediction_count": len(records),
        "instance_ids": [record["instance_id"] for record in records],
        "candidate_patches_path": str(candidate_path),
    }


def _load_prediction_records(path: Path) -> list[dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"predictions file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"predictions file is not valid JSON: {error}") from error

    if not isinstance(payload, list):
        raise ConfigError("predictions must be a JSON array")
    return [_prediction_record(item, index) for index, item in enumerate(payload)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _prediction_record(value: Any, index: int) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ConfigError(f"predictions[{index}] must be an object")
    record = {}
    for field in SWE_BENCH_PREDICTION_FIELDS:
        field_value = value.get(field)
        if not isinstance(field_value, str) or not field_value:
            raise ConfigError(f"predictions[{index}].{field} must be a non-empty string")
        record[field] = field_value
    return record


def _validate_prediction_records(
    records: list[dict[str, str]],
    *,
    allowed_instance_ids: set[str],
) -> None:
    if not records:
        raise ConfigError("predictions must contain at least one record")

    seen = set()
    for record in records:
        instance_id = record["instance_id"]
        if instance_id in seen:
            raise ConfigError(f"prediction instance_id {instance_id} is duplicated")
        seen.add(instance_id)
        if instance_id not in allowed_instance_ids:
            raise ConfigError(
                f"prediction instance_id {instance_id} is not in course handoff"
            )


def _task_ids(handoff: dict[str, Any]) -> set[str]:
    tasks = handoff["tasks"]
    assert isinstance(tasks, list)
    return {str(task["id"]) for task in tasks}
