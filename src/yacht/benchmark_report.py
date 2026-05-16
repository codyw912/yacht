from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.regatta import ConfigError
from yacht.schemas import (
    SchemaValidationError,
    validate_benchmark_scorecard_document,
    validate_task_attempt_scorecard_document,
)
from yacht.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


def render_benchmark_report(logbook_dir: Path, output_format: str = "text") -> str:
    scorecard_path = logbook_dir / BENCHMARK_SCORECARD_PATH
    if not scorecard_path.exists():
        raise ConfigError(f"benchmark scorecard artifact not found: {scorecard_path}")
    scorecard = _load_scorecard(scorecard_path)
    try:
        validate_benchmark_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"benchmark scorecard artifact is invalid: {error}"
        ) from error
    task_attempt_scorecard = _load_task_attempt_scorecard(logbook_dir)
    if output_format == "markdown":
        return _render_scorecard_markdown(scorecard, task_attempt_scorecard)
    return _render_scorecard(scorecard, task_attempt_scorecard)


def _load_scorecard(path: Path) -> dict[str, Any]:
    return _load_json(path, "benchmark scorecard artifact")


def _load_task_attempt_scorecard(logbook_dir: Path) -> dict[str, Any] | None:
    path = logbook_dir / TASK_ATTEMPT_SCORECARD_PATH
    if not path.exists():
        return None
    scorecard = _load_json(path, "task attempt scorecard artifact")
    try:
        validate_task_attempt_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"task attempt scorecard artifact is invalid: {error}"
        ) from error
    return scorecard


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _render_scorecard(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> str:
    summary = scorecard["summary"]
    lines = [
        f"Benchmark scorecard: {scorecard['regatta']} / {scorecard['course']}",
        f"Status: {scorecard['status']}",
        "Comparisons: "
        f"{summary['total_comparisons']} | "
        f"Vessels: {summary['total_vessels']} | "
        f"Measured: {summary['measured_vessels']} | "
        f"Missing: {summary['missing_result_vessels']}",
        "",
        "comparison | baseline | challenger | resolved_delta | rate_delta | "
        "measured | missing | eligible | preflight",
    ]
    lines.extend(_comparison_row(comparison) for comparison in scorecard["comparisons"])
    if task_attempt_scorecard is not None:
        lines.extend(_usage_lines(task_attempt_scorecard))
    return "\n".join(lines) + "\n"


def _render_scorecard_markdown(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> str:
    summary = scorecard["summary"]
    lines = [
        "## Benchmark scorecard",
        "",
        f"- Regatta: {scorecard['regatta']}",
        f"- Course: {scorecard['course']}",
        f"- Status: {scorecard['status']}",
        f"- Comparisons: {summary['total_comparisons']}",
        f"- Vessels: {summary['total_vessels']}",
        f"- Measured: {summary['measured_vessels']}",
        f"- Missing: {summary['missing_result_vessels']}",
        "",
        "| Comparison | Baseline | Challenger | Resolved delta | Rate delta | "
        "Measured | Missing | Eligible | Preflight |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        _comparison_markdown_row(comparison) for comparison in scorecard["comparisons"]
    )
    if task_attempt_scorecard is not None:
        lines.extend(_usage_markdown_lines(task_attempt_scorecard))
    return "\n".join(lines) + "\n"


def _comparison_row(comparison: dict[str, Any]) -> str:
    delta = comparison["delta"]
    summary = comparison["summary"]
    return (
        f"{comparison['name']} | "
        f"{delta['baseline_vessel']} | "
        f"{delta['challenger_vessel']} | "
        f"{_signed_int(delta['resolved_instances_delta'])} | "
        f"{_signed_float(delta['resolution_rate_delta'])} | "
        f"{summary['measured_vessels']}/{summary['total_vessels']} | "
        f"{summary['missing_result_vessels']} | "
        f"{summary['eligible_vessels']} | "
        f"{_preflight_reasons(comparison)}"
    )


def _comparison_markdown_row(comparison: dict[str, Any]) -> str:
    delta = comparison["delta"]
    summary = comparison["summary"]
    return (
        f"| {comparison['name']} | "
        f"{delta['baseline_vessel']} | "
        f"{delta['challenger_vessel']} | "
        f"{_signed_int(delta['resolved_instances_delta'])} | "
        f"{_signed_float(delta['resolution_rate_delta'])} | "
        f"{summary['measured_vessels']}/{summary['total_vessels']} | "
        f"{summary['missing_result_vessels']} | "
        f"{summary['eligible_vessels']} | "
        f"{_preflight_reasons(comparison)} |"
    )


def _signed_int(value: int) -> str:
    return f"{value:+d}"


def _signed_float(value: float) -> str:
    return f"{value:+.3f}"


def _preflight_reasons(comparison: dict[str, Any]) -> str:
    counts: dict[str, int] = {}
    for vessel in comparison["vessels"]:
        reason = str(vessel["preflight_reason"])
        counts[reason] = counts.get(reason, 0) + 1
    return ", ".join(f"{reason}:{count}" for reason, count in counts.items())


def _usage_lines(scorecard: dict[str, Any]) -> list[str]:
    summary = scorecard["summary"]
    lines = [
        "",
        "Agent usage: "
        f"Attempts: {summary['total_attempts']} | "
        f"Failed: {summary['failed_attempts']} | "
        f"Tool calls: {summary['total_tool_calls']} | "
        f"Tokens: {summary['total_tokens']} | "
        f"Cost: {_cost(summary['total_cost'])} | "
        f"Duration: {_duration(summary['total_duration_seconds'])}",
        "",
        "comparison | vessel | attempts | failed | tools | tokens | cost | duration",
    ]
    lines.extend(
        _usage_row(comparison, vessel)
        for comparison, vessel in _usage_vessels(scorecard)
    )
    return lines


def _usage_markdown_lines(scorecard: dict[str, Any]) -> list[str]:
    summary = scorecard["summary"]
    lines = [
        "",
        "## Agent usage",
        "",
        f"- Attempts: {summary['total_attempts']}",
        f"- Failed attempts: {summary['failed_attempts']}",
        f"- Tool calls: {summary['total_tool_calls']}",
        f"- Tokens: {summary['total_tokens']}",
        f"- Cost: {_cost(summary['total_cost'])}",
        f"- Duration: {_duration(summary['total_duration_seconds'])}",
        "",
        "| Comparison | Vessel | Attempts | Failed | Tools | Tokens | Cost | Duration |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {_usage_row(comparison, vessel)} |"
        for comparison, vessel in _usage_vessels(scorecard)
    )
    return lines


def _usage_vessels(
    scorecard: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (comparison, vessel)
        for comparison in scorecard["comparisons"]
        for vessel in comparison["vessels"]
    ]


def _usage_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{vessel['task_attempts']} | "
        f"{vessel['failed_attempts']} | "
        f"{_tool_counts(vessel['tool_call_counts'])} | "
        f"{vessel['total_tokens']} | "
        f"{_cost(vessel['total_cost'])} | "
        f"{_duration(vessel['total_duration_seconds'])}"
    )


def _tool_counts(value: dict[str, int]) -> str:
    if not value:
        return "-"
    return ", ".join(f"{tool}:{count}" for tool, count in value.items())


def _cost(value: float) -> str:
    return f"{float(value):.6f}"


def _duration(value: float) -> str:
    return f"{float(value):.3f}s"
