from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError
from yacht.contracts.schemas import SchemaValidationError, validate_task_attempt_document
from yacht.courses.swe_bench.predictions import write_swe_bench_prediction_records


def write_swe_bench_predictions_from_attempts(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    attempts = _selected_attempts(
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
        comparison_name=comparison_name,
    )
    records = [_prediction_record(attempt, vessel_name) for attempt in attempts]
    return write_swe_bench_prediction_records(
        config_path=config_path,
        records=records,
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
    )


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
        raise ConfigError(f"task attempt artifact is not valid JSON: {error}") from error
    if not isinstance(attempt, dict):
        raise ConfigError("task attempt artifact must be a JSON object")
    try:
        validate_task_attempt_document(attempt)
    except SchemaValidationError as error:
        raise ConfigError(f"task attempt artifact is invalid: {error}") from error
    return attempt


def _prediction_record(
    attempt: dict[str, Any],
    vessel_name: str,
) -> dict[str, str]:
    if attempt["status"] != "completed":
        raise ConfigError(
            "task attempt "
            f"{attempt['comparison']}/{vessel_name}/{attempt['task']['id']} "
            "is not completed"
        )
    return {
        "instance_id": str(attempt["task"]["id"]),
        "model_name_or_path": vessel_name,
        "model_patch": _model_patch_from_response(
            str(attempt["agent"]["response"]),
            attempt,
        ),
    }


def _model_patch_from_response(response: str, attempt: dict[str, Any]) -> str:
    payload = _json_response(response)
    if isinstance(payload, dict):
        model_patch = payload.get("model_patch")
        if isinstance(model_patch, str) and model_patch.strip():
            return model_patch

    if _looks_like_unified_diff(response):
        return response

    raise ConfigError(
        "task attempt "
        f"{attempt['comparison']}/{attempt['vessel']}/{attempt['task']['id']} "
        "response must be a JSON object with non-empty model_patch or a unified diff"
    )


def _json_response(response: str) -> Any:
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    for candidate in _fenced_json_candidates(response):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _fenced_json_candidates(response: str) -> tuple[str, ...]:
    return tuple(
        match.group("body").strip()
        for match in re.finditer(
            r"```(?:json)?\s*\n(?P<body>.*?)\n```",
            response,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )


def _looks_like_unified_diff(response: str) -> bool:
    return (
        "diff --git " in response
        and "\n--- " in response
        and "\n+++ " in response
    )
