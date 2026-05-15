from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.regatta import ConfigError
from yacht.schemas import (
    SchemaValidationError,
    validate_smoke_readiness_report_document,
    validate_task_attempt_scorecard_document,
)
from yacht.smoke_readiness_report import SMOKE_READINESS_REPORT_PATH
from yacht.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


def render_smoke_report(logbook_dir: Path, output_format: str = "text") -> str:
    readiness = _load_readiness(logbook_dir)
    scorecard = _load_scorecard(logbook_dir)
    if output_format == "markdown":
        return _render_markdown(readiness, scorecard)
    return _render_text(readiness, scorecard)


def _load_readiness(logbook_dir: Path) -> dict[str, Any]:
    path = logbook_dir / SMOKE_READINESS_REPORT_PATH
    if not path.exists():
        raise ConfigError(f"smoke readiness report artifact not found: {path}")
    readiness = _load_json_object(path, "smoke readiness report artifact")
    try:
        validate_smoke_readiness_report_document(readiness)
    except SchemaValidationError as error:
        raise ConfigError(
            f"smoke readiness report artifact is invalid: {error}"
        ) from error
    return readiness


def _load_scorecard(logbook_dir: Path) -> dict[str, Any]:
    path = logbook_dir / TASK_ATTEMPT_SCORECARD_PATH
    if not path.exists():
        raise ConfigError(f"task attempt scorecard artifact not found: {path}")
    scorecard = _load_json_object(path, "task attempt scorecard artifact")
    try:
        validate_task_attempt_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"task attempt scorecard artifact is invalid: {error}"
        ) from error
    return scorecard


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _render_text(readiness: dict[str, Any], scorecard: dict[str, Any]) -> str:
    summary = readiness["summary"]
    scorecard_summary = scorecard["summary"]
    lines = [
        f"Real smoke report: {readiness['regatta']} / {readiness['course']}",
        f"Status: {readiness['status']}",
        "Vessels: "
        f"{summary['total_vessels']} | "
        f"Ready: {summary['ready_vessels']} | "
        f"Blocked: {summary['blocked_vessels']} | "
        f"Attempts: {scorecard_summary['total_attempts']} | "
        f"Failed: {scorecard_summary['failed_attempts']} | "
        f"Tool calls: {scorecard_summary['total_tool_calls']} | "
        f"Tokens: {scorecard_summary['total_tokens']} | "
        f"Cost: {_cost(scorecard_summary['total_cost'])}",
        "",
        "comparison | vessel | status | preflight | attempts | tools | expected | "
        "missing | tokens | cost | details",
    ]
    lines.extend(
        _vessel_row(comparison, vessel, scorecard)
        for comparison, vessel in _vessels(readiness)
    )
    return "\n".join(lines) + "\n"


def _render_markdown(readiness: dict[str, Any], scorecard: dict[str, Any]) -> str:
    summary = readiness["summary"]
    scorecard_summary = scorecard["summary"]
    lines = [
        "## Real smoke report",
        "",
        f"- Regatta: {readiness['regatta']}",
        f"- Course: {readiness['course']}",
        f"- Status: {readiness['status']}",
        f"- Vessels: {summary['total_vessels']}",
        f"- Ready: {summary['ready_vessels']}",
        f"- Blocked: {summary['blocked_vessels']}",
        f"- Attempts: {scorecard_summary['total_attempts']}",
        f"- Failed attempts: {scorecard_summary['failed_attempts']}",
        f"- Tool calls: {scorecard_summary['total_tool_calls']}",
        f"- Tokens: {scorecard_summary['total_tokens']}",
        f"- Cost: {_cost(scorecard_summary['total_cost'])}",
        "",
        "| Comparison | Vessel | Status | Preflight | Attempts | Tools | Expected | "
        "Missing | Tokens | Cost | Details |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    lines.extend(
        f"| {_vessel_row(comparison, vessel, scorecard)} |"
        for comparison, vessel in _vessels(readiness)
    )
    return "\n".join(lines) + "\n"


def _vessels(readiness: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (comparison, vessel)
        for comparison in readiness["comparisons"]
        for vessel in comparison["vessels"]
    ]


def _vessel_row(
    comparison: dict[str, Any],
    readiness_vessel: dict[str, Any],
    scorecard: dict[str, Any],
) -> str:
    scorecard_vessel = _scorecard_vessel(
        scorecard,
        str(comparison["name"]),
        str(readiness_vessel["name"]),
    )
    return (
        f"{comparison['name']} | "
        f"{readiness_vessel['name']} | "
        f"{readiness_vessel['status']} | "
        f"{readiness_vessel['preflight_status']} | "
        f"{readiness_vessel['task_attempt_status']} | "
        f"{_tool_counts(readiness_vessel['tool_call_counts'])} | "
        f"{_tool_list(readiness_vessel['expected_tool_calls'])} | "
        f"{_tool_list(readiness_vessel['missing_expected_tool_calls'])} | "
        f"{scorecard_vessel['total_tokens']} | "
        f"{_cost(scorecard_vessel['total_cost'])} | "
        f"{_details(readiness_vessel)}"
    )


def _scorecard_vessel(
    scorecard: dict[str, Any],
    comparison_name: str,
    vessel_name: str,
) -> dict[str, Any]:
    for comparison in scorecard["comparisons"]:
        if comparison["name"] != comparison_name:
            continue
        for vessel in comparison["vessels"]:
            if vessel["name"] == vessel_name:
                return vessel
    raise ConfigError(
        "task attempt scorecard is missing vessel "
        f"{comparison_name}/{vessel_name}"
    )


def _tool_counts(value: dict[str, int]) -> str:
    if not value:
        return "-"
    return ", ".join(f"{tool}:{count}" for tool, count in value.items())


def _tool_list(value: list[str]) -> str:
    return ", ".join(value) if value else "-"


def _cost(value: float) -> str:
    return f"{float(value):.6f}"


def _details(vessel: dict[str, Any]) -> str:
    if not vessel["reasons"]:
        return "-"
    return "; ".join(str(reason) for reason in vessel["reasons"])
