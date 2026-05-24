from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_benchmark_scorecard_document,
    validate_task_attempt_scorecard_document,
)
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


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
    return render_benchmark_aggregate_document(aggregate, output_format)


def render_benchmark_aggregate_document(
    aggregate: dict[str, Any],
    output_format: str = "text",
) -> str:
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
    run_summaries = _aggregate_runs(comparison_name, vessel_names, runs)
    return {
        "name": comparison_name,
        "baseline": vessel_names[0],
        "challenger": vessel_names[1],
        "vessels": vessels,
        "runs": run_summaries,
        "delta": _aggregate_delta(vessels),
        "delta_statistics": _delta_statistics(run_summaries),
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
    run_vessels = [
        _run_vessel(comparison_name, vessel_name, run) for run in runs
    ]
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
        "statistics": _vessel_statistics(run_vessels),
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


def _aggregate_runs(
    comparison_name: str,
    vessel_names: list[str],
    runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    run_summaries = []
    for index, run in enumerate(runs, start=1):
        vessels = [
            _run_vessel(comparison_name, vessel_name, run)
            for vessel_name in vessel_names
        ]
        run_summaries.append(
            {
                "index": index,
                "logbook": str(run["logbook"]),
                "vessels": vessels,
                "delta": _run_delta(vessels),
            }
        )
    return run_summaries


def _vessel_statistics(run_vessels: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resolution_rate": _stats(
            [float(vessel["resolution_rate"]) for vessel in run_vessels],
            digits=3,
        ),
        "tokens": _stats([int(vessel["tokens"]) for vessel in run_vessels]),
        "cost": _stats(
            [float(vessel["cost"]) for vessel in run_vessels],
            digits=6,
        ),
        "duration_seconds": _stats(
            [float(vessel["duration_seconds"]) for vessel in run_vessels],
            digits=3,
        ),
        "tool_calls": _stats([int(vessel["tool_calls"]) for vessel in run_vessels]),
    }


def _delta_statistics(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [run["delta"] for run in run_summaries]
    return {
        "baseline_vessel": deltas[0]["baseline_vessel"],
        "challenger_vessel": deltas[0]["challenger_vessel"],
        "resolved_instances_delta": _stats(
            [int(delta["resolved_instances_delta"]) for delta in deltas],
        ),
        "resolution_rate_delta": _stats(
            [float(delta["resolution_rate_delta"]) for delta in deltas],
            digits=3,
        ),
        "tokens_delta": _stats([int(delta["tokens_delta"]) for delta in deltas]),
        "cost_delta": _stats(
            [float(delta["cost_delta"]) for delta in deltas],
            digits=6,
        ),
        "duration_seconds_delta": _stats(
            [float(delta["duration_seconds_delta"]) for delta in deltas],
            digits=3,
        ),
        "tool_calls_delta": _stats(
            [int(delta["tool_calls_delta"]) for delta in deltas],
        ),
    }


def _stats(values: list[float | int], *, digits: int = 3) -> dict[str, Any]:
    if not values:
        return {"runs": 0, "mean": 0.0, "stdev": 0.0, "min": 0, "max": 0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "runs": len(values),
        "mean": round(mean, digits),
        "stdev": round(math.sqrt(variance), digits),
        "min": round(min(values), digits),
        "max": round(max(values), digits),
    }


def _run_vessel(
    comparison_name: str,
    vessel_name: str,
    run: dict[str, Any],
) -> dict[str, Any]:
    vessel = _vessel_by_name(
        _comparison_by_name(run["scorecard"], comparison_name),
        vessel_name,
    )
    usage_vessel = _usage_vessel(run["attempt_scorecard"], comparison_name, vessel_name)
    submitted = int(vessel["submitted_instances"])
    resolved = int(vessel["resolved_instances"])
    payload = {
        "name": vessel_name,
        "status": str(vessel["status"]),
        "submitted_instances": submitted,
        "resolved_instances": resolved,
        "resolution_rate": resolved / submitted if submitted else 0.0,
        "tokens": 0,
        "cost": 0.0,
        "duration_seconds": 0.0,
        "tool_calls": 0,
    }
    if usage_vessel is not None:
        payload.update(
            {
                "tokens": int(usage_vessel["total_tokens"]),
                "cost": round(float(usage_vessel["total_cost"]), 6),
                "duration_seconds": round(
                    float(usage_vessel["total_duration_seconds"]),
                    3,
                ),
                "tool_calls": int(usage_vessel["tool_call_count"]),
            }
        )
    return payload


def _run_delta(vessels: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = vessels[0]
    challenger = vessels[1]
    return {
        "baseline_vessel": baseline["name"],
        "challenger_vessel": challenger["name"],
        "resolved_instances_delta": int(challenger["resolved_instances"])
        - int(baseline["resolved_instances"]),
        "resolution_rate_delta": float(challenger["resolution_rate"])
        - float(baseline["resolution_rate"]),
        "tokens_delta": int(challenger["tokens"]) - int(baseline["tokens"]),
        "cost_delta": round(float(challenger["cost"]) - float(baseline["cost"]), 6),
        "duration_seconds_delta": round(
            float(challenger["duration_seconds"]) - float(baseline["duration_seconds"]),
            3,
        ),
        "tool_calls_delta": int(challenger["tool_calls"])
        - int(baseline["tool_calls"]),
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
        "Decision summary:",
        "comparison | resolution | tokens | cost | duration",
    ]
    lines.extend(
        _decision_summary_row(comparison) for comparison in aggregate["comparisons"]
    )
    lines.extend(
        [
            "",
            "Aggregate deltas:",
            "comparison | baseline | challenger | resolved_delta | rate_delta | "
            "tokens_delta | cost_delta | duration_delta | tool_calls_delta",
        ]
    )
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
        lines.extend(
            _vessel_row(comparison, vessel) for vessel in comparison["vessels"]
        )
    lines.extend(
        [
            "",
            "Aggregate statistics by vessel:",
            "comparison | vessel | rate_mean | rate_range | tokens_mean | "
            "tokens_range | cost_mean | cost_range | duration_mean | "
            "duration_range | tool_calls_mean | tool_calls_range",
        ]
    )
    for comparison in aggregate["comparisons"]:
        lines.extend(
            _vessel_statistics_row(comparison, vessel)
            for vessel in comparison["vessels"]
        )
    lines.extend(
        [
            "",
            "Aggregate variability by vessel:",
            "comparison | vessel | rate_stdev | tokens_stdev | cost_stdev | "
            "duration_stdev | tool_calls_stdev",
        ]
    )
    for comparison in aggregate["comparisons"]:
        lines.extend(
            _vessel_variability_row(comparison, vessel)
            for vessel in comparison["vessels"]
        )
    lines.extend(
        [
            "",
            "Aggregate delta statistics:",
            "comparison | baseline | challenger | rate_mean | rate_range | "
            "tokens_mean | tokens_range | cost_mean | cost_range | "
            "duration_mean | duration_range | tool_calls_mean | tool_calls_range",
        ]
    )
    lines.extend(
        _delta_statistics_row(comparison) for comparison in aggregate["comparisons"]
    )
    lines.extend(
        [
            "",
            "Aggregate delta variability:",
            "comparison | baseline | challenger | resolved_stdev | rate_stdev | "
            "tokens_stdev | cost_stdev | duration_stdev | tool_calls_stdev",
        ]
    )
    lines.extend(
        _delta_variability_row(comparison) for comparison in aggregate["comparisons"]
    )
    lines.extend(
        [
            "",
            "Aggregate runs by vessel:",
            "comparison | run | vessel | status | submitted | resolved | rate | "
            "tokens | cost | duration | tool_calls | logbook",
        ]
    )
    for comparison in aggregate["comparisons"]:
        for run in comparison["runs"]:
            lines.extend(
                _run_vessel_row(comparison, run, vessel) for vessel in run["vessels"]
            )
    return "\n".join(lines) + "\n"


def _render_markdown(aggregate: dict[str, Any]) -> str:
    lines = [
        "## Benchmark aggregate",
        "",
        f"- Regatta: {aggregate['regatta']}",
        f"- Course: {aggregate['course']}",
        f"- Runs: {aggregate['run_count']}",
        "",
        "## Decision summary",
        "",
    ]
    lines.extend(
        f"- {_decision_summary_row(comparison)}"
        for comparison in aggregate["comparisons"]
    )
    lines.extend(
        [
            "",
            "## Aggregate deltas",
            "",
            "| Comparison | Baseline | Challenger | Resolved delta | Rate delta | "
            "Tokens delta | Cost delta | Duration delta | Tool calls delta |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
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
    lines.extend(
        [
            "",
            "## Aggregate statistics by vessel",
            "",
            "| Comparison | Vessel | Rate mean | Rate range | Tokens mean | "
            "Tokens range | Cost mean | Cost range | Duration mean | "
            "Duration range | Tool calls mean | Tool calls range |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for comparison in aggregate["comparisons"]:
        lines.extend(
            f"| {_vessel_statistics_row(comparison, vessel)} |"
            for vessel in comparison["vessels"]
        )
    lines.extend(
        [
            "",
            "## Aggregate variability by vessel",
            "",
            "| Comparison | Vessel | Rate stdev | Tokens stdev | Cost stdev | "
            "Duration stdev | Tool calls stdev |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for comparison in aggregate["comparisons"]:
        lines.extend(
            f"| {_vessel_variability_row(comparison, vessel)} |"
            for vessel in comparison["vessels"]
        )
    lines.extend(
        [
            "",
            "## Aggregate delta statistics",
            "",
            "| Comparison | Baseline | Challenger | Rate mean | Rate range | "
            "Tokens mean | Tokens range | Cost mean | Cost range | "
            "Duration mean | Duration range | Tool calls mean | Tool calls range |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {_delta_statistics_row(comparison)} |"
        for comparison in aggregate["comparisons"]
    )
    lines.extend(
        [
            "",
            "## Aggregate delta variability",
            "",
            "| Comparison | Baseline | Challenger | Resolved stdev | Rate stdev | "
            "Tokens stdev | Cost stdev | Duration stdev | Tool calls stdev |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {_delta_variability_row(comparison)} |"
        for comparison in aggregate["comparisons"]
    )
    lines.extend(
        [
            "",
            "## Aggregate runs by vessel",
            "",
            "| Comparison | Run | Vessel | Status | Submitted | Resolved | Rate | "
            "Tokens | Cost | Duration | Tool calls | Logbook |",
            "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for comparison in aggregate["comparisons"]:
        for run in comparison["runs"]:
            lines.extend(
                f"| {_run_vessel_row(comparison, run, vessel)} |"
                for vessel in run["vessels"]
            )
    return "\n".join(lines) + "\n"


def _decision_summary_row(comparison: dict[str, Any]) -> str:
    delta = comparison["delta"]
    return " | ".join(
        [
            str(comparison["name"]),
            _resolution_decision(delta),
            _resource_decision("tokens", int(delta["tokens_delta"])),
            _resource_decision("cost", float(delta["cost_delta"])),
            _resource_decision("duration", float(delta["duration_seconds_delta"])),
        ]
    )


def _resolution_decision(delta: dict[str, Any]) -> str:
    resolved_delta = int(delta["resolved_instances_delta"])
    rate_delta = float(delta["resolution_rate_delta"])
    if resolved_delta > 0:
        label = "better"
    elif resolved_delta < 0:
        label = "worse"
    elif rate_delta > 0:
        label = "better"
    elif rate_delta < 0:
        label = "worse"
    else:
        label = "tied"
    return (
        f"resolution {label} "
        f"({_signed_int(resolved_delta)} resolved, {_signed_rate(rate_delta)} rate)"
    )


def _resource_decision(label: str, value: int | float) -> str:
    numeric_value = float(value)
    if numeric_value < 0:
        verdict = "better"
    elif numeric_value > 0:
        verdict = "worse"
    else:
        verdict = "tied"
    if label == "cost":
        rendered = _signed_cost(float(value))
    elif label == "duration":
        rendered = _signed_duration(float(value))
    else:
        rendered = _signed_int(int(value))
    return f"{label} {verdict} ({rendered})"


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


def _vessel_statistics_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    stats = vessel["statistics"]
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{_stats_rate_mean(stats['resolution_rate'])} | "
        f"{_stats_rate_range(stats['resolution_rate'])} | "
        f"{_stats_number_mean(stats['tokens'])} | "
        f"{_stats_number_range(stats['tokens'])} | "
        f"{_stats_cost_mean(stats['cost'])} | "
        f"{_stats_cost_range(stats['cost'])} | "
        f"{_stats_duration_mean(stats['duration_seconds'])} | "
        f"{_stats_duration_range(stats['duration_seconds'])} | "
        f"{_stats_number_mean(stats['tool_calls'])} | "
        f"{_stats_number_range(stats['tool_calls'])}"
    )


def _delta_statistics_row(comparison: dict[str, Any]) -> str:
    stats = comparison["delta_statistics"]
    return (
        f"{comparison['name']} | "
        f"{stats['baseline_vessel']} | "
        f"{stats['challenger_vessel']} | "
        f"{_stats_signed_rate_mean(stats['resolution_rate_delta'])} | "
        f"{_stats_signed_rate_range(stats['resolution_rate_delta'])} | "
        f"{_stats_signed_number_mean(stats['tokens_delta'])} | "
        f"{_stats_signed_number_range(stats['tokens_delta'])} | "
        f"{_stats_signed_cost_mean(stats['cost_delta'])} | "
        f"{_stats_signed_cost_range(stats['cost_delta'])} | "
        f"{_stats_signed_duration_mean(stats['duration_seconds_delta'])} | "
        f"{_stats_signed_duration_range(stats['duration_seconds_delta'])} | "
        f"{_stats_signed_number_mean(stats['tool_calls_delta'])} | "
        f"{_stats_signed_number_range(stats['tool_calls_delta'])}"
    )


def _vessel_variability_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    stats = vessel["statistics"]
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{_stats_rate_stdev(stats['resolution_rate'])} | "
        f"{_stats_number_stdev(stats['tokens'])} | "
        f"{_stats_cost_stdev(stats['cost'])} | "
        f"{_stats_duration_stdev(stats['duration_seconds'])} | "
        f"{_stats_number_stdev(stats['tool_calls'])}"
    )


def _delta_variability_row(comparison: dict[str, Any]) -> str:
    stats = comparison["delta_statistics"]
    return (
        f"{comparison['name']} | "
        f"{stats['baseline_vessel']} | "
        f"{stats['challenger_vessel']} | "
        f"{_stats_number_stdev(stats['resolved_instances_delta'])} | "
        f"{_stats_rate_stdev(stats['resolution_rate_delta'])} | "
        f"{_stats_number_stdev(stats['tokens_delta'])} | "
        f"{_stats_cost_stdev(stats['cost_delta'])} | "
        f"{_stats_duration_stdev(stats['duration_seconds_delta'])} | "
        f"{_stats_number_stdev(stats['tool_calls_delta'])}"
    )


def _run_vessel_row(
    comparison: dict[str, Any],
    run: dict[str, Any],
    vessel: dict[str, Any],
) -> str:
    return (
        f"{comparison['name']} | "
        f"{run['index']} | "
        f"{vessel['name']} | "
        f"{vessel['status']} | "
        f"{vessel['submitted_instances']} | "
        f"{vessel['resolved_instances']} | "
        f"{_rate(vessel['resolution_rate'])} | "
        f"{vessel['tokens']} | "
        f"{_cost(vessel['cost'])} | "
        f"{_duration(vessel['duration_seconds'])} | "
        f"{vessel['tool_calls']} | "
        f"{run['logbook']}"
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


def _stats_rate_mean(stats: dict[str, Any]) -> str:
    return _rate(stats["mean"])


def _stats_rate_stdev(stats: dict[str, Any]) -> str:
    return _rate(stats["stdev"])


def _stats_rate_range(stats: dict[str, Any]) -> str:
    return f"{_rate(stats['min'])}..{_rate(stats['max'])}"


def _stats_number_mean(stats: dict[str, Any]) -> str:
    return f"{float(stats['mean']):.1f}"


def _stats_number_stdev(stats: dict[str, Any]) -> str:
    return f"{float(stats['stdev']):.1f}"


def _stats_number_range(stats: dict[str, Any]) -> str:
    return f"{stats['min']}..{stats['max']}"


def _stats_cost_mean(stats: dict[str, Any]) -> str:
    return _cost(stats["mean"])


def _stats_cost_stdev(stats: dict[str, Any]) -> str:
    return _cost(stats["stdev"])


def _stats_cost_range(stats: dict[str, Any]) -> str:
    return f"{_cost(stats['min'])}..{_cost(stats['max'])}"


def _stats_duration_mean(stats: dict[str, Any]) -> str:
    return _duration(stats["mean"])


def _stats_duration_stdev(stats: dict[str, Any]) -> str:
    return _duration(stats["stdev"])


def _stats_duration_range(stats: dict[str, Any]) -> str:
    return f"{_duration(stats['min'])}..{_duration(stats['max'])}"


def _stats_signed_rate_mean(stats: dict[str, Any]) -> str:
    return _signed_rate(stats["mean"])


def _stats_signed_rate_range(stats: dict[str, Any]) -> str:
    return f"{_signed_rate(stats['min'])}..{_signed_rate(stats['max'])}"


def _stats_signed_number_mean(stats: dict[str, Any]) -> str:
    return f"{float(stats['mean']):+.1f}"


def _stats_signed_number_range(stats: dict[str, Any]) -> str:
    return f"{int(stats['min']):+d}..{int(stats['max']):+d}"


def _stats_signed_cost_mean(stats: dict[str, Any]) -> str:
    return _signed_cost(stats["mean"])


def _stats_signed_cost_range(stats: dict[str, Any]) -> str:
    return f"{_signed_cost(stats['min'])}..{_signed_cost(stats['max'])}"


def _stats_signed_duration_mean(stats: dict[str, Any]) -> str:
    return _signed_duration(stats["mean"])


def _stats_signed_duration_range(stats: dict[str, Any]) -> str:
    return f"{_signed_duration(stats['min'])}..{_signed_duration(stats['max'])}"
