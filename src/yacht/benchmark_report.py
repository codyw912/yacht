from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.regatta import ConfigError
from yacht.schemas import SchemaValidationError
from yacht.schemas import validate_benchmark_scorecard_document


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
    if output_format == "markdown":
        return _render_scorecard_markdown(scorecard)
    return _render_scorecard(scorecard)


def _load_scorecard(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"benchmark scorecard artifact is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ConfigError("benchmark scorecard artifact must be a JSON object")
    return payload


def _render_scorecard(scorecard: dict[str, Any]) -> str:
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
    return "\n".join(lines) + "\n"


def _render_scorecard_markdown(scorecard: dict[str, Any]) -> str:
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
