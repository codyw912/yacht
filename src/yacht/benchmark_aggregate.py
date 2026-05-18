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


BENCHMARK_AGGREGATE_SCHEMA = "yacht.benchmark-aggregate.v1"
BENCHMARK_AGGREGATE_PATH = Path("benchmark-aggregate.json")


def build_benchmark_aggregate(logbook_dirs: list[Path]) -> dict[str, Any]:
    if not logbook_dirs:
        raise ConfigError("benchmark aggregate requires at least one --logbook")
    runs = [_load_run(logbook_dir) for logbook_dir in logbook_dirs]
    first_scorecard = runs[0]["scorecard"]
    _validate_compatible_runs(runs)
    comparisons = [
        _aggregate_comparison(str(comparison["name"]), runs)
        for comparison in first_scorecard["comparisons"]
    ]
    return {
        "schema": BENCHMARK_AGGREGATE_SCHEMA,
        "regatta": str(first_scorecard["regatta"]),
        "course": str(first_scorecard["course"]),
        "run_count": len(runs),
        "logbooks": [str(run["logbook"]) for run in runs],
        "comparisons": comparisons,
    }


def render_benchmark_aggregate(
    logbook_dirs: list[Path],
    output_format: str = "text",
) -> str:
    aggregate = build_benchmark_aggregate(logbook_dirs)
    if output_format == "json":
        return json.dumps(aggregate, indent=2) + "\n"
    if output_format == "markdown":
        return _render_markdown(aggregate)
    return _render_text(aggregate)


def _load_run(logbook_dir: Path) -> dict[str, Any]:
    scorecard_path = logbook_dir / BENCHMARK_SCORECARD_PATH
    if not scorecard_path.exists():
        raise ConfigError(f"benchmark scorecard artifact not found: {scorecard_path}")
    scorecard = _load_json(scorecard_path, "benchmark scorecard artifact")
    try:
        validate_benchmark_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"benchmark scorecard artifact is invalid: {scorecard_path}: {error}"
        ) from error
    return {
        "logbook": logbook_dir,
        "scorecard": scorecard,
        "attempt_scorecard": _load_attempt_scorecard(logbook_dir),
    }


def _load_attempt_scorecard(logbook_dir: Path) -> dict[str, Any] | None:
    path = logbook_dir / TASK_ATTEMPT_SCORECARD_PATH
    if not path.exists():
        return None
    scorecard = _load_json(path, "task attempt scorecard artifact")
    try:
        validate_task_attempt_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"task attempt scorecard artifact is invalid: {path}: {error}"
        ) from error
    return scorecard


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object: {path}")
    return payload


def _validate_compatible_runs(runs: list[dict[str, Any]]) -> None:
    first = runs[0]["scorecard"]
    expected_comparisons = [str(item["name"]) for item in first["comparisons"]]
    for run in runs[1:]:
        scorecard = run["scorecard"]
        if scorecard["regatta"] != first["regatta"]:
            raise ConfigError("benchmark aggregate logbooks must share regatta")
        if scorecard["course"] != first["course"]:
            raise ConfigError("benchmark aggregate logbooks must share course")
        comparison_names = [str(item["name"]) for item in scorecard["comparisons"]]
        if comparison_names != expected_comparisons:
            raise ConfigError("benchmark aggregate logbooks must share comparisons")


def _aggregate_comparison(
    comparison_name: str,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    first_comparison = _comparison_by_name(runs[0]["scorecard"], comparison_name)
    vessel_names = [str(vessel["name"]) for vessel in first_comparison["vessels"]]
    vessels = [
        _aggregate_vessel(comparison_name, vessel_name, runs)
        for vessel_name in vessel_names
    ]
    return {
        "name": comparison_name,
        "baseline": vessel_names[0],
        "challenger": vessel_names[1],
        "vessels": vessels,
        "delta": _aggregate_delta(vessels),
    }


def _aggregate_vessel(
    comparison_name: str,
    vessel_name: str,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    measured_runs = 0
    submitted = 0
    resolved = 0
    eligible_runs = 0
    usage_runs = 0
    tokens = 0
    cost = 0.0
    duration = 0.0
    tool_calls = 0
    for run in runs:
        vessel = _vessel_by_name(
            _comparison_by_name(run["scorecard"], comparison_name),
            vessel_name,
        )
        if vessel["eligible_for_benchmark"]:
            eligible_runs += 1
        if vessel["status"] == "measured":
            measured_runs += 1
            submitted += int(vessel["submitted_instances"])
            resolved += int(vessel["resolved_instances"])
        usage_vessel = _usage_vessel(run["attempt_scorecard"], comparison_name, vessel_name)
        if usage_vessel is not None:
            usage_runs += 1
            tokens += int(usage_vessel["total_tokens"])
            cost += float(usage_vessel["total_cost"])
            duration += float(usage_vessel["total_duration_seconds"])
            tool_calls += int(usage_vessel["tool_call_count"])
    return {
        "name": vessel_name,
        "runs": len(runs),
        "eligible_runs": eligible_runs,
        "measured_runs": measured_runs,
        "submitted_instances": submitted,
        "resolved_instances": resolved,
        "resolution_rate": resolved / submitted if submitted else 0.0,
        "usage_runs": usage_runs,
        "total_tokens": tokens,
        "total_cost": round(cost, 6),
        "total_duration_seconds": round(duration, 3),
        "total_tool_calls": tool_calls,
    }


def _aggregate_delta(vessels: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = vessels[0]
    challenger = vessels[1]
    return {
        "baseline_vessel": baseline["name"],
        "challenger_vessel": challenger["name"],
        "resolved_instances_delta": int(challenger["resolved_instances"])
        - int(baseline["resolved_instances"]),
        "resolution_rate_delta": float(challenger["resolution_rate"])
        - float(baseline["resolution_rate"]),
        "tokens_delta": int(challenger["total_tokens"]) - int(baseline["total_tokens"]),
        "cost_delta": round(
            float(challenger["total_cost"]) - float(baseline["total_cost"]),
            6,
        ),
        "duration_seconds_delta": round(
            float(challenger["total_duration_seconds"])
            - float(baseline["total_duration_seconds"]),
            3,
        ),
        "tool_calls_delta": int(challenger["total_tool_calls"])
        - int(baseline["total_tool_calls"]),
    }


def _comparison_by_name(scorecard: dict[str, Any], name: str) -> dict[str, Any]:
    for comparison in scorecard["comparisons"]:
        if comparison["name"] == name:
            return comparison
    raise ConfigError(f"benchmark scorecard missing comparison {name}")


def _vessel_by_name(comparison: dict[str, Any], name: str) -> dict[str, Any]:
    for vessel in comparison["vessels"]:
        if vessel["name"] == name:
            return vessel
    raise ConfigError(f"benchmark scorecard missing vessel {name}")


def _usage_vessel(
    attempt_scorecard: dict[str, Any] | None,
    comparison_name: str,
    vessel_name: str,
) -> dict[str, Any] | None:
    if attempt_scorecard is None:
        return None
    for comparison in attempt_scorecard["comparisons"]:
        if comparison["name"] != comparison_name:
            continue
        for vessel in comparison["vessels"]:
            if vessel["name"] == vessel_name:
                return vessel
    return None


def _render_text(aggregate: dict[str, Any]) -> str:
    lines = [
        f"Benchmark aggregate: {aggregate['regatta']} / {aggregate['course']}",
        f"Runs: {aggregate['run_count']}",
        "",
        "Aggregate deltas:",
        "comparison | baseline | challenger | resolved_delta | rate_delta | "
        "tokens_delta | cost_delta | duration_delta | tool_calls_delta",
    ]
    lines.extend(_delta_row(comparison) for comparison in aggregate["comparisons"])
    lines.extend(
        [
            "",
            "Aggregate usage by vessel:",
            "comparison | vessel | runs | measured | submitted | resolved | rate | "
            "usage_runs | tokens | cost | duration | tool_calls",
        ]
    )
    for comparison in aggregate["comparisons"]:
        lines.extend(_vessel_row(comparison, vessel) for vessel in comparison["vessels"])
    return "\n".join(lines) + "\n"


def _render_markdown(aggregate: dict[str, Any]) -> str:
    lines = [
        "## Benchmark aggregate",
        "",
        f"- Regatta: {aggregate['regatta']}",
        f"- Course: {aggregate['course']}",
        f"- Runs: {aggregate['run_count']}",
        "",
        "## Aggregate deltas",
        "",
        "| Comparison | Baseline | Challenger | Resolved delta | Rate delta | "
        "Tokens delta | Cost delta | Duration delta | Tool calls delta |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(f"| {_delta_row(comparison)} |" for comparison in aggregate["comparisons"])
    lines.extend(
        [
            "",
            "## Aggregate usage by vessel",
            "",
            "| Comparison | Vessel | Runs | Measured | Submitted | Resolved | Rate | "
            "Usage runs | Tokens | Cost | Duration | Tool calls |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for comparison in aggregate["comparisons"]:
        lines.extend(
            f"| {_vessel_row(comparison, vessel)} |"
            for vessel in comparison["vessels"]
        )
    return "\n".join(lines) + "\n"


def _delta_row(comparison: dict[str, Any]) -> str:
    delta = comparison["delta"]
    return (
        f"{comparison['name']} | "
        f"{delta['baseline_vessel']} | "
        f"{delta['challenger_vessel']} | "
        f"{_signed_int(delta['resolved_instances_delta'])} | "
        f"{_signed_rate(delta['resolution_rate_delta'])} | "
        f"{_signed_int(delta['tokens_delta'])} | "
        f"{_signed_cost(delta['cost_delta'])} | "
        f"{_signed_duration(delta['duration_seconds_delta'])} | "
        f"{_signed_int(delta['tool_calls_delta'])}"
    )


def _vessel_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{vessel['runs']} | "
        f"{vessel['measured_runs']} | "
        f"{vessel['submitted_instances']} | "
        f"{vessel['resolved_instances']} | "
        f"{_rate(vessel['resolution_rate'])} | "
        f"{vessel['usage_runs']} | "
        f"{vessel['total_tokens']} | "
        f"{_cost(vessel['total_cost'])} | "
        f"{_duration(vessel['total_duration_seconds'])} | "
        f"{vessel['total_tool_calls']}"
    )


def _signed_int(value: int) -> str:
    return f"{value:+d}"


def _signed_rate(value: float) -> str:
    return f"{float(value):+.3f}"


def _signed_cost(value: float) -> str:
    return f"{float(value):+.6f}"


def _signed_duration(value: float) -> str:
    return f"{float(value):+.3f}s"


def _rate(value: float) -> str:
    return f"{float(value):.3f}"


def _cost(value: float) -> str:
    return f"{float(value):.6f}"


def _duration(value: float) -> str:
    return f"{float(value):.3f}s"
