from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from yacht.courses.attempts import selected_task_attempts
from yacht.courses.swe_bench.predictions import write_swe_bench_prediction_records
from yacht.domain.model import ConfigError


def write_swe_bench_predictions_from_attempts(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    attempts = selected_task_attempts(
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
    return "diff --git " in response and "\n--- " in response and "\n+++ " in response
