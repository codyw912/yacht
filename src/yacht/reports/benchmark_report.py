from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.reports.benchmark_aggregate import BENCHMARK_AGGREGATE_PATH
from yacht.reports.benchmark_aggregate import BENCHMARK_AGGREGATE_SCHEMA
from yacht.reports.benchmark_aggregate import build_benchmark_aggregate
from yacht.reports.benchmark_aggregate import render_benchmark_aggregate_document
from yacht.workflows.benchmark_grading_collection import (
    BENCHMARK_GRADING_COLLECTION_PATH,
)
from yacht.workflows.benchmark_launch import BENCHMARK_LAUNCH_RESULT_PATH
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.reports.html_report import render_benchmark_html
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_benchmark_scorecard_document,
    validate_task_attempt_document,
    validate_task_attempt_scorecard_document,
)
from yacht.reports.surface_summary import format_surface_summary
from yacht.reports.surface_summary import load_logbook_surfaces
from yacht.courses.artifacts import (
    candidate_patches_path,
    grading_report_path,
)
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


def render_benchmark_report(
    logbook_dir: Path,
    output_format: str = "text",
    *,
    vessel_name: str | None = None,
    task_id: str | None = None,
) -> str:
    scorecard_path = logbook_dir / BENCHMARK_SCORECARD_PATH
    if not scorecard_path.exists():
        aggregate_path = logbook_dir / BENCHMARK_AGGREGATE_PATH
        if aggregate_path.exists():
            if vessel_name is not None or task_id is not None:
                raise ConfigError(
                    "benchmark report filters require a single-run benchmark "
                    "scorecard; repeated-run aggregate reports cannot be filtered"
                )
            return _render_aggregate_report(aggregate_path, output_format)
        raise ConfigError(
            f"benchmark scorecard artifact not found: {scorecard_path}; "
            f"benchmark aggregate artifact not found: {aggregate_path}"
        )
    scorecard = _load_scorecard(scorecard_path)
    try:
        validate_benchmark_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"benchmark scorecard artifact is invalid: {error}"
        ) from error
    task_attempt_scorecard = _load_task_attempt_scorecard(logbook_dir)
    _validate_filters(scorecard, vessel_name, task_id)
    if output_format == "html":
        if vessel_name is not None or task_id is not None:
            raise ConfigError(
                "--vessel and --task filters apply to text and markdown "
                "formats; the html report always includes every vessel and task"
            )
        return render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=task_attempt_scorecard,
            logbook_dir=logbook_dir,
        )
    if output_format == "markdown":
        return _render_scorecard_markdown(
            logbook_dir,
            scorecard,
            task_attempt_scorecard,
            vessel_name,
            task_id,
        )
    return _render_scorecard(
        logbook_dir,
        scorecard,
        task_attempt_scorecard,
        vessel_name,
        task_id,
    )


def _render_aggregate_report(path: Path, output_format: str) -> str:
    aggregate = _load_json(path, "benchmark aggregate artifact")
    if aggregate.get("schema") != BENCHMARK_AGGREGATE_SCHEMA:
        raise ConfigError(
            "benchmark aggregate artifact is invalid: "
            f"schema must be {BENCHMARK_AGGREGATE_SCHEMA}"
        )
    aggregate = _aggregate_with_run_details(aggregate)
    return render_benchmark_aggregate_document(aggregate, output_format)


def _aggregate_with_run_details(aggregate: dict[str, Any]) -> dict[str, Any]:
    if all(
        _comparison_has_run_statistics(comparison)
        for comparison in aggregate["comparisons"]
    ):
        return aggregate
    logbooks = aggregate.get("logbooks")
    if not isinstance(logbooks, list) or not all(
        isinstance(logbook, str) for logbook in logbooks
    ):
        return aggregate
    return build_benchmark_aggregate([Path(logbook) for logbook in logbooks])


def _comparison_has_run_statistics(comparison: dict[str, Any]) -> bool:
    return (
        "runs" in comparison
        and _statistics_include_stdev(comparison.get("delta_statistics"))
        and all(
            _statistics_include_stdev(vessel.get("statistics"))
            for vessel in comparison.get("vessels", [])
        )
    )


def _statistics_include_stdev(statistics: Any) -> bool:
    if not isinstance(statistics, dict):
        return False
    metric_keys = [
        key for key in statistics if key not in {"baseline_vessel", "challenger_vessel"}
    ]
    return bool(metric_keys) and all(
        isinstance(statistics.get(key), dict) and "stdev" in statistics[key]
        for key in metric_keys
    )


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
    logbook_dir: Path,
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
    vessel_name: str | None,
    task_id: str | None,
) -> str:
    summary = scorecard["summary"]
    lines = [
        f"Benchmark scorecard: {scorecard['regatta']} / {scorecard['course']}",
        f"Status: {scorecard['status']}",
        *_surface_text_lines(logbook_dir),
        "Comparisons: "
        f"{summary['total_comparisons']} | "
        f"Vessels: {summary['total_vessels']} | "
        f"Measured: {summary['measured_vessels']} | "
        f"Missing: {summary['missing_result_vessels']}",
        _usage_summary_line(task_attempt_scorecard),
        *_decision_summary_lines(scorecard, task_attempt_scorecard),
        _artifact_line(logbook_dir),
    ]
    lines.extend(_filter_lines(vessel_name, task_id))
    lines.extend(_repetition_budget_lines(scorecard))
    lines.extend(_notable_delta_lines(scorecard, task_attempt_scorecard))
    lines.extend(
        [
            "",
            "comparison | baseline | challenger | resolved_delta | rate_delta | "
            "measured | missing | eligible | preflight",
        ]
    )
    lines.extend(_comparison_row(comparison) for comparison in scorecard["comparisons"])
    lines.extend(_outcome_lines(scorecard, vessel_name, task_id))
    if task_attempt_scorecard is not None:
        lines.extend(
            _usage_lines(
                task_attempt_scorecard,
                scorecard,
                logbook_dir,
                vessel_name,
                task_id,
            )
        )
        lines.extend(
            _task_outcome_lines(
                scorecard,
                task_attempt_scorecard,
                vessel_name,
                task_id,
            )
        )
        lines.extend(
            _artifact_drilldown_lines(
                logbook_dir,
                scorecard,
                task_attempt_scorecard,
                _load_grading_collection(logbook_dir),
                vessel_name,
                task_id,
            )
        )
    return "\n".join(lines) + "\n"


def _render_scorecard_markdown(
    logbook_dir: Path,
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
    vessel_name: str | None,
    task_id: str | None,
) -> str:
    summary = scorecard["summary"]
    lines = [
        "## Benchmark scorecard",
        "",
        f"- Regatta: {scorecard['regatta']}",
        f"- Course: {scorecard['course']}",
        f"- Status: {scorecard['status']}",
        *_surface_markdown_lines(logbook_dir),
        f"- Comparisons: {summary['total_comparisons']}",
        f"- Vessels: {summary['total_vessels']}",
        f"- Measured: {summary['measured_vessels']}",
        f"- Missing: {summary['missing_result_vessels']}",
        *_usage_summary_markdown_lines(task_attempt_scorecard),
        "",
        "## Decision summary",
        "",
        *_decision_summary_markdown_lines(scorecard, task_attempt_scorecard),
        *_filter_markdown_lines(vessel_name, task_id),
        *_repetition_budget_markdown_lines(scorecard),
        "",
        "## Notable deltas",
        "",
        *_notable_delta_markdown_lines(scorecard, task_attempt_scorecard),
        "",
        "## Artifacts",
        "",
        f"- Logbook: {logbook_dir}",
        f"- Benchmark scorecard: {logbook_dir / BENCHMARK_SCORECARD_PATH}",
        f"- Task attempt scorecard: {logbook_dir / TASK_ATTEMPT_SCORECARD_PATH}",
        f"- Launch result: {logbook_dir / BENCHMARK_LAUNCH_RESULT_PATH}",
        f"- Grading collection: {logbook_dir / BENCHMARK_GRADING_COLLECTION_PATH}",
        "",
        "| Comparison | Baseline | Challenger | Resolved delta | Rate delta | "
        "Measured | Missing | Eligible | Preflight |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        _comparison_markdown_row(comparison) for comparison in scorecard["comparisons"]
    )
    lines.extend(_outcome_markdown_lines(scorecard, vessel_name, task_id))
    if task_attempt_scorecard is not None:
        lines.extend(
            _usage_markdown_lines(
                task_attempt_scorecard,
                scorecard,
                logbook_dir,
                vessel_name,
                task_id,
            )
        )
        lines.extend(
            _task_outcome_markdown_lines(
                scorecard,
                task_attempt_scorecard,
                vessel_name,
                task_id,
            )
        )
        lines.extend(
            _artifact_drilldown_markdown_lines(
                logbook_dir,
                scorecard,
                task_attempt_scorecard,
                _load_grading_collection(logbook_dir),
                vessel_name,
                task_id,
            )
        )
    return "\n".join(lines) + "\n"


def _load_grading_collection(logbook_dir: Path) -> dict[str, Any] | None:
    path = logbook_dir / BENCHMARK_GRADING_COLLECTION_PATH
    if not path.exists():
        return None
    return _load_json(path, "benchmark grading collection artifact")


def _surface_text_lines(logbook_dir: Path) -> list[str]:
    summary = format_surface_summary(load_logbook_surfaces(logbook_dir))
    if summary is None:
        return []
    return [f"Surfaces: {summary}"]


def _surface_markdown_lines(logbook_dir: Path) -> list[str]:
    summary = format_surface_summary(load_logbook_surfaces(logbook_dir))
    if summary is None:
        return []
    return [f"- Surfaces: {summary}"]


def _validate_filters(
    scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> None:
    if vessel_name is not None and not any(
        str(vessel["name"]) == vessel_name for _, vessel in _vessels(scorecard)
    ):
        raise ConfigError(
            f"benchmark report vessel filter matched no vessel: {vessel_name}"
        )
    if task_id is not None and not any(
        _vessel_has_task(vessel, task_id) for _, vessel in _vessels(scorecard)
    ):
        raise ConfigError(f"benchmark report task filter matched no task: {task_id}")
    if (
        vessel_name is not None
        and task_id is not None
        and not any(
            _matches_filters(vessel, vessel_name, task_id)
            for _, vessel in _vessels(scorecard)
        )
    ):
        raise ConfigError(
            "benchmark report filters matched no vessel/task pair: "
            f"{vessel_name} / {task_id}"
        )


def _filter_lines(vessel_name: str | None, task_id: str | None) -> list[str]:
    parts = _filter_parts(vessel_name, task_id)
    if not parts:
        return []
    return [f"Filter: {' | '.join(parts)}"]


def _filter_markdown_lines(
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    parts = _filter_parts(vessel_name, task_id)
    if not parts:
        return []
    return [f"- Filter: {' | '.join(parts)}"]


def _filter_parts(vessel_name: str | None, task_id: str | None) -> list[str]:
    parts = []
    if vessel_name is not None:
        parts.append(f"vessel={vessel_name}")
    if task_id is not None:
        parts.append(f"task={task_id}")
    return parts


OPTIONAL_STOPPING_WARNING = (
    "Budget a fresh run at one of these sizes and commit to it. Adding "
    "repetitions to this comparison and re-testing until it crosses p<0.05 "
    "is optional stopping: the p-value would no longer mean 0.05."
)


def _repetition_budget_lines(scorecard: dict[str, Any]) -> list[str]:
    plans = _repetition_budget_plans(scorecard)
    if not plans:
        return []
    lines = [
        "",
        "Repetition budget (80% power, no difference demonstrated yet):",
        "comparison | assumed split | discordant pairs needed | repetitions",
    ]
    lines.extend(plans)
    lines.extend(["", OPTIONAL_STOPPING_WARNING])
    return lines


def _repetition_budget_markdown_lines(scorecard: dict[str, Any]) -> list[str]:
    plans = _repetition_budget_plans(scorecard)
    if not plans:
        return []
    return [
        "",
        "## Repetition budget",
        "",
        "80% power, for comparisons where no difference was demonstrated.",
        "",
        "| Comparison | Assumed split | Discordant pairs needed | Repetitions |",
        "| --- | --- | ---: | ---: |",
        *[f"| {plan} |" for plan in plans],
        "",
        f"_{OPTIONAL_STOPPING_WARNING}_",
    ]


def _repetition_budget_plans(scorecard: dict[str, Any]) -> list[str]:
    rows = []
    for comparison in scorecard["comparisons"]:
        statistics = comparison.get("statistics")
        if not isinstance(statistics, dict):
            continue
        guidance = statistics.get("repetition_guidance")
        if not isinstance(guidance, dict):
            continue
        for plan in guidance.get("plans", []):
            rows.append(
                f"{comparison['name']} | "
                f"challenger wins {float(plan['assumed_favored_fraction']):.0%} "
                "of discordant | "
                f"{_planned_pairs(plan)} | {_planned_repetitions(plan)}"
            )
    return rows


def _planned_pairs(plan: dict[str, Any]) -> str:
    pairs = plan.get("discordant_pairs_needed")
    if pairs is None:
        return "unreachable at this effect size"
    return str(pairs)


def _planned_repetitions(plan: dict[str, Any]) -> str:
    repetitions = plan.get("repetitions")
    if repetitions is None:
        return "not estimable (no discordant tasks observed)"
    bounds = plan.get("repetitions_range")
    if not isinstance(bounds, dict):
        return str(repetitions)
    low = bounds.get("low")
    high = bounds.get("high")
    if low is None and high is None:
        return str(repetitions)
    high_label = "unbounded" if high is None else str(high)
    return f"{repetitions} ({low}–{high_label} across rate uncertainty)"


def _notable_delta_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> list[str]:
    return [
        "",
        "Notable deltas:",
        *[
            _notable_delta_row(comparison, task_attempt_scorecard)
            for comparison in scorecard["comparisons"]
        ],
    ]


def _notable_delta_markdown_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> list[str]:
    return [
        f"- {_notable_delta_row(comparison, task_attempt_scorecard)}"
        for comparison in scorecard["comparisons"]
    ]


def _notable_delta_row(
    comparison: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> str:
    delta = comparison["delta"]
    baseline_name = str(delta["baseline_vessel"])
    challenger_name = str(delta["challenger_vessel"])
    versus = f"{comparison['name']}: {challenger_name} vs {baseline_name}"
    recorded_note = _recorded_baseline_note(comparison)
    if recorded_note is not None:
        versus = f"{versus} [{recorded_note}]"
    delivery = comparison.get("delivery")
    if isinstance(delivery, dict) and delivery.get("status") != "delivered":
        status = str(delivery.get("status")).replace("-", " ")
        versus = f"{versus} [treatment {status}]"
    parts = [
        versus,
        f"resolved {_signed_int(delta['resolved_instances_delta'])}",
        f"rate {_signed_float(delta['resolution_rate_delta'])}",
    ]
    usage_delta = _usage_delta(
        task_attempt_scorecard,
        comparison_name=str(comparison["name"]),
        baseline_name=baseline_name,
        challenger_name=challenger_name,
        recorded_usage=_recorded_baseline_usage(comparison),
    )
    if usage_delta is not None:
        parts.extend(
            [
                f"tokens {_signed_int(usage_delta['tokens'])}",
                f"cost {_signed_cost(usage_delta['cost'])}",
                f"duration {_signed_duration(usage_delta['duration'])}",
                f"tool_calls {_signed_int(usage_delta['tool_calls'])}",
            ]
        )
    return " | ".join(parts)


def _decision_summary_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> list[str]:
    lines = [
        "",
        "Decision summary:",
        "comparison | resolution | tokens | cost | duration | delivery",
    ]
    lines.extend(
        _decision_summary_row(comparison, task_attempt_scorecard)
        for comparison in scorecard["comparisons"]
    )
    return lines


def _decision_summary_markdown_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> list[str]:
    return [
        f"- {_decision_summary_row(comparison, task_attempt_scorecard)}"
        for comparison in scorecard["comparisons"]
    ]


def _decision_summary_row(
    comparison: dict[str, Any],
    task_attempt_scorecard: dict[str, Any] | None,
) -> str:
    delta = comparison["delta"]
    baseline_name = str(delta["baseline_vessel"])
    challenger_name = str(delta["challenger_vessel"])
    usage_delta = _usage_delta(
        task_attempt_scorecard,
        comparison_name=str(comparison["name"]),
        baseline_name=baseline_name,
        challenger_name=challenger_name,
        recorded_usage=_recorded_baseline_usage(comparison),
    )
    confound = (
        " [outcome-confounded]"
        if float(delta.get("resolution_rate_delta", 0.0)) != 0.0
        and usage_delta is not None
        else ""
    )
    return " | ".join(
        [
            str(comparison["name"]),
            _resolution_decision(delta, comparison.get("statistics")),
            _usage_decision(usage_delta, "tokens", "tokens") + confound,
            _usage_decision(usage_delta, "cost", "cost") + confound,
            _usage_decision(usage_delta, "duration", "duration") + confound,
            _delivery_decision(comparison.get("delivery")),
        ]
    )


def _delivery_decision(delivery: dict[str, Any] | None) -> str:
    if not isinstance(delivery, dict):
        return "delivery -"
    status = str(delivery.get("status"))
    rates = ", ".join(
        f"{tool.get('tool')} {tool.get('invoked_attempts', '?')}/"
        f"{tool.get('measured_attempts')}"
        for tool in delivery.get("tools", ())
        if tool.get("status") == "measured"
    )
    if status == "delivered":
        return f"delivered ({rates})"
    if status == "not-delivered":
        return f"NOT DELIVERED ({rates})" if rates else "NOT DELIVERED"
    return "delivery unmeasured"


def _resolution_decision(
    delta: dict[str, Any],
    statistics: dict[str, Any] | None = None,
) -> str:
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
    decision = (
        f"resolution {label} "
        f"({_signed_int(resolved_delta)} resolved, {_signed_float(rate_delta)} rate)"
    )
    evidence = _resolution_evidence(statistics)
    if evidence is not None:
        decision = f"{decision} [{evidence}]"
    return decision


def _resolution_evidence(statistics: dict[str, Any] | None) -> str | None:
    if not isinstance(statistics, dict):
        return None
    paired = statistics.get("paired")
    if not isinstance(paired, dict):
        return None
    grade = paired.get("grade")
    discordant = int(paired.get("discordant_baseline_only", 0)) + int(
        paired.get("discordant_challenger_only", 0)
    )
    if grade == "insufficient-evidence":
        minimum = paired.get("min_significant_discordant")
        return (
            "insufficient evidence: observation only "
            f"({discordant} discordant task(s), need >={minimum})"
        )
    return _graded_evidence(grade, paired)


def _graded_evidence(grade: Any, paired: dict[str, Any]) -> str | None:
    p_value = float(paired.get("p_value", 1.0))
    if grade == "not-distinguishable":
        return f"not distinguishable from noise (p={p_value:.3f})"
    if grade == "evidence-of-difference":
        return f"evidence of difference (p={p_value:.3f})"
    return None


def _usage_decision(
    usage_delta: dict[str, int | float] | None,
    key: str,
    label: str,
) -> str:
    if usage_delta is None:
        return f"{label} unavailable"
    value = usage_delta[key]
    if float(value) < 0:
        verdict = "better"
    elif float(value) > 0:
        verdict = "worse"
    else:
        verdict = "tied"
    return f"{label} {verdict} ({_usage_delta_value(key, value)})"


def _usage_delta_value(key: str, value: int | float) -> str:
    if key == "cost":
        return _signed_cost(float(value))
    if key == "duration":
        return _signed_duration(float(value))
    return _signed_int(int(value))


def _usage_delta(
    task_attempt_scorecard: dict[str, Any] | None,
    *,
    comparison_name: str,
    baseline_name: str,
    challenger_name: str,
    recorded_usage: dict[str, Any] | None = None,
) -> dict[str, int | float] | None:
    if task_attempt_scorecard is None:
        return None
    usage = {
        (str(comparison["name"]), str(vessel["name"])): vessel
        for comparison in task_attempt_scorecard["comparisons"]
        for vessel in comparison["vessels"]
    }
    baseline = usage.get((comparison_name, baseline_name))
    challenger = usage.get((comparison_name, challenger_name))
    if baseline is None:
        baseline = recorded_usage
    if baseline is None or challenger is None:
        return None
    return {
        "tokens": int(challenger["total_tokens"]) - int(baseline["total_tokens"]),
        "cost": float(challenger["total_cost"]) - float(baseline["total_cost"]),
        "duration": float(challenger["total_duration_seconds"])
        - float(baseline["total_duration_seconds"]),
        "tool_calls": int(challenger["tool_call_count"])
        - int(baseline["tool_call_count"]),
    }


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


def _signed_cost(value: float) -> str:
    return f"{value:+.6f}"


def _signed_duration(value: float) -> str:
    return f"{value:+.3f}s"


def _preflight_reasons(comparison: dict[str, Any]) -> str:
    counts: dict[str, int] = {}
    for vessel in comparison["vessels"]:
        reason = str(vessel.get("preflight_reason", "recorded-baseline"))
        counts[reason] = counts.get(reason, 0) + 1
    return ", ".join(f"{reason}:{count}" for reason, count in counts.items())


def _recorded_baseline_vessel(comparison: dict[str, Any]) -> dict[str, Any] | None:
    for vessel in comparison["vessels"]:
        if vessel.get("status") == "recorded":
            return vessel
    return None


def _recorded_baseline_note(comparison: dict[str, Any]) -> str | None:
    vessel = _recorded_baseline_vessel(comparison)
    if vessel is None:
        return None
    source = vessel.get("baseline_source", {})
    run_date = source.get("run_date")
    if isinstance(run_date, str) and run_date:
        return f"recorded baseline from {run_date[:10]}"
    return "recorded baseline, run date unknown"


def _recorded_baseline_usage(comparison: dict[str, Any]) -> dict[str, Any] | None:
    vessel = _recorded_baseline_vessel(comparison)
    if vessel is None:
        return None
    usage = vessel.get("baseline_source", {}).get("usage")
    if not isinstance(usage, dict):
        return None
    required = (
        "total_tokens",
        "total_cost",
        "total_duration_seconds",
        "tool_call_count",
    )
    if not all(isinstance(usage.get(key), int | float) for key in required):
        return None
    return usage


def _outcome_lines(
    scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "Benchmark outcomes by vessel:",
        "comparison | vessel | status | submitted | resolved | rate | preflight",
    ]
    lines.extend(
        _outcome_row(comparison, vessel)
        for comparison, vessel in _filtered_vessels(scorecard, vessel_name, task_id)
    )
    return lines


def _outcome_markdown_lines(
    scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "## Benchmark outcomes by vessel",
        "",
        "| Comparison | Vessel | Status | Submitted | Resolved | Rate | Preflight |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        f"| {_outcome_row(comparison, vessel)} |"
        for comparison, vessel in _filtered_vessels(scorecard, vessel_name, task_id)
    )
    return lines


def _vessels(scorecard: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (comparison, vessel)
        for comparison in scorecard["comparisons"]
        for vessel in comparison["vessels"]
    ]


def _filtered_vessels(
    scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (comparison, vessel)
        for comparison, vessel in _vessels(scorecard)
        if _matches_filters(vessel, vessel_name, task_id)
    ]


def _matches_filters(
    vessel: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> bool:
    if vessel_name is not None and str(vessel["name"]) != vessel_name:
        return False
    if task_id is not None and not _vessel_has_task(vessel, task_id):
        return False
    return True


def _vessel_has_task(vessel: dict[str, Any], task_id: str) -> bool:
    return task_id in {str(value) for value in _task_ids(vessel)}


def _task_ids(vessel: dict[str, Any]) -> list[Any]:
    return [
        *vessel.get("resolved_ids", []),
        *vessel.get("unresolved_ids", []),
    ]


def _outcome_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{vessel['status']} | "
        f"{vessel['submitted_instances']} | "
        f"{vessel['resolved_instances']} | "
        f"{_rate(vessel['resolution_rate'])} | "
        f"{vessel.get('preflight_reason', 'recorded-baseline')}"
    )


def _usage_lines(
    scorecard: dict[str, Any],
    benchmark_scorecard: dict[str, Any],
    logbook_dir: Path,
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "Agent usage by vessel:",
        "comparison | vessel | harnesses | attempts | failed | tools | tokens | "
        "cost | duration",
    ]
    lines.extend(
        _usage_row(comparison, vessel)
        for comparison, vessel in _usage_vessels(
            scorecard,
            benchmark_scorecard,
            vessel_name,
            task_id,
        )
    )
    lines.extend(
        [
            "",
            "Efficiency by vessel (usage per resolved task):",
            "comparison | vessel | resolved | tokens/resolution | cost/resolution",
        ]
    )
    lines.extend(
        _efficiency_row(comparison, vessel, benchmark_scorecard)
        for comparison, vessel in _usage_vessels(
            scorecard,
            benchmark_scorecard,
            vessel_name,
            task_id,
        )
    )
    task_rows = _task_usage_rows(
        scorecard,
        benchmark_scorecard,
        logbook_dir,
        vessel_name,
        task_id,
    )
    if task_rows:
        lines.extend(
            [
                "",
                "Agent usage by task:",
                "comparison | vessel | task | tools | tokens | cost | duration | "
                "attempt_artifact",
            ]
        )
        lines.extend(_task_usage_row(row) for row in task_rows)
    return lines


def _usage_markdown_lines(
    scorecard: dict[str, Any],
    benchmark_scorecard: dict[str, Any],
    logbook_dir: Path,
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "## Agent usage by vessel",
        "",
        "| Comparison | Vessel | Harnesses | Attempts | Failed | Tools | Tokens | "
        "Cost | Duration |",
        "| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {_usage_row(comparison, vessel)} |"
        for comparison, vessel in _usage_vessels(
            scorecard,
            benchmark_scorecard,
            vessel_name,
            task_id,
        )
    )
    lines.extend(
        [
            "",
            "## Efficiency by vessel (usage per resolved task)",
            "",
            "| Comparison | Vessel | Resolved | Tokens/resolution | Cost/resolution |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {_efficiency_row(comparison, vessel, benchmark_scorecard)} |"
        for comparison, vessel in _usage_vessels(
            scorecard,
            benchmark_scorecard,
            vessel_name,
            task_id,
        )
    )
    task_rows = _task_usage_rows(
        scorecard,
        benchmark_scorecard,
        logbook_dir,
        vessel_name,
        task_id,
    )
    if task_rows:
        lines.extend(
            [
                "",
                "## Agent usage by task",
                "",
                "| Comparison | Vessel | Task | Tools | Tokens | Cost | Duration | "
                "Attempt artifact |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        lines.extend(f"| {_task_usage_row(row)} |" for row in task_rows)
    return lines


def _usage_summary_line(scorecard: dict[str, Any] | None) -> str:
    if scorecard is None:
        return f"Usage: unavailable (missing {TASK_ATTEMPT_SCORECARD_PATH})"
    summary = scorecard["summary"]
    return (
        "Usage: "
        f"Attempts: {summary['total_attempts']} | "
        f"Failed: {summary['failed_attempts']} | "
        f"Tool calls: {summary['total_tool_calls']} | "
        f"Tokens: {summary['total_tokens']} | "
        f"Cost: {_cost(summary['total_cost'])} | "
        f"Duration: {_duration(summary['total_duration_seconds'])}"
    )


def _usage_summary_markdown_lines(scorecard: dict[str, Any] | None) -> list[str]:
    if scorecard is None:
        return [f"- Usage: unavailable (missing {TASK_ATTEMPT_SCORECARD_PATH})"]
    summary = scorecard["summary"]
    return [
        f"- Attempts: {summary['total_attempts']}",
        f"- Failed attempts: {summary['failed_attempts']}",
        f"- Tool calls: {summary['total_tool_calls']}",
        f"- Tokens: {summary['total_tokens']}",
        f"- Cost: {_cost(summary['total_cost'])}",
        f"- Duration: {_duration(summary['total_duration_seconds'])}",
    ]


def _artifact_line(logbook_dir: Path) -> str:
    return (
        f"Artifacts: logbook={logbook_dir} | "
        f"scorecard={logbook_dir / BENCHMARK_SCORECARD_PATH} | "
        f"attempts={logbook_dir / TASK_ATTEMPT_SCORECARD_PATH} | "
        f"launch={logbook_dir / BENCHMARK_LAUNCH_RESULT_PATH} | "
        f"grading={logbook_dir / BENCHMARK_GRADING_COLLECTION_PATH}"
    )


def _usage_vessels(
    scorecard: dict[str, Any],
    benchmark_scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    benchmark_vessels = {
        (str(comparison["name"]), str(vessel["name"])): vessel
        for comparison, vessel in _vessels(benchmark_scorecard)
    }
    return [
        (comparison, vessel)
        for comparison, vessel in _vessels(scorecard)
        if _matches_filters(
            benchmark_vessels[(str(comparison["name"]), str(vessel["name"]))],
            vessel_name,
            task_id,
        )
    ]


def _usage_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{_harnesses(vessel)} | "
        f"{vessel['task_attempts']} | "
        f"{vessel['failed_attempts']} | "
        f"{_tool_counts(vessel['tool_call_counts'])} | "
        f"{vessel['total_tokens']} | "
        f"{_cost(vessel['total_cost'])} | "
        f"{_duration(vessel['total_duration_seconds'])}"
    )


def _efficiency_row(
    comparison: dict[str, Any],
    vessel: dict[str, Any],
    benchmark_scorecard: dict[str, Any],
) -> str:
    resolved = _resolved_instances(
        benchmark_scorecard,
        str(comparison["name"]),
        str(vessel["name"]),
    )
    if resolved:
        tokens = f"{int(vessel['total_tokens']) / resolved:.1f}"
        cost = _cost(float(vessel["total_cost"]) / resolved)
    else:
        tokens = "n/a (0 resolved)"
        cost = "n/a (0 resolved)"
    return f"{comparison['name']} | {vessel['name']} | {resolved} | {tokens} | {cost}"


def _resolved_instances(
    benchmark_scorecard: dict[str, Any],
    comparison_name: str,
    vessel_name: str,
) -> int:
    for comparison, vessel in _vessels(benchmark_scorecard):
        if (
            str(comparison["name"]) == comparison_name
            and str(vessel["name"]) == vessel_name
        ):
            return int(vessel.get("resolved_instances", 0))
    return 0


def _task_usage_rows(
    scorecard: dict[str, Any],
    benchmark_scorecard: dict[str, Any],
    logbook_dir: Path,
    vessel_name: str | None,
    task_id: str | None,
) -> list[dict[str, str]]:
    benchmark_vessels = {
        (str(comparison["name"]), str(vessel["name"])): vessel
        for comparison, vessel in _vessels(benchmark_scorecard)
    }
    rows = []
    for comparison, vessel in _vessels(scorecard):
        comparison_name = str(comparison["name"])
        current_vessel_name = str(vessel["name"])
        benchmark_vessel = benchmark_vessels[(comparison_name, current_vessel_name)]
        if not _matches_filters(benchmark_vessel, vessel_name, task_id):
            continue
        for artifact in vessel["artifact_paths"]:
            attempt = _load_task_attempt_artifact(
                logbook_dir,
                str(artifact),
            )
            if attempt is None:
                continue
            current_task_id = str(attempt["task"]["id"])
            if task_id is not None and current_task_id != task_id:
                continue
            rows.append(
                {
                    "comparison": comparison_name,
                    "vessel": current_vessel_name,
                    "task": current_task_id,
                    "tools": _tool_counts(_tool_call_counts(attempt)),
                    "tokens": str(attempt["metrics"]["tokens"]),
                    "cost": _optional_cost(_attempt_cost(attempt)),
                    "duration": _duration(
                        float(attempt["metrics"]["duration_seconds"])
                    ),
                    "attempt_artifact": str(artifact),
                }
            )
    return rows


def _load_task_attempt_artifact(
    logbook_dir: Path,
    artifact_path: str,
) -> dict[str, Any] | None:
    path = _resolve_artifact_path(logbook_dir, artifact_path)
    if not path.exists():
        return None
    attempt = _load_json(path, "task attempt artifact")
    try:
        validate_task_attempt_document(attempt)
    except SchemaValidationError as error:
        raise ConfigError(
            f"task attempt artifact is invalid: {path}: {error}"
        ) from error
    return attempt


def _resolve_artifact_path(logbook_dir: Path, artifact_path: str) -> Path:
    path = Path(artifact_path)
    if path.is_absolute():
        return path
    candidate = logbook_dir.parent / path
    if candidate.exists():
        return candidate
    return path


def _tool_call_counts(attempt: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tool_call in attempt["agent"].get("tool_calls", []):
        tool_name = str(tool_call)
        counts[tool_name] = counts.get(tool_name, 0) + 1
    return counts


def _attempt_cost(attempt: dict[str, Any]) -> float | None:
    machine_evidence = attempt["agent"].get("machine_evidence", {})
    if not isinstance(machine_evidence, dict):
        return None
    cost = machine_evidence.get("cost", {})
    if not isinstance(cost, dict):
        return None
    total = cost.get("total")
    if isinstance(total, int | float):
        return float(total)
    return None


def _optional_cost(value: float | None) -> str:
    if value is None:
        return "-"
    return _cost(value)


def _task_usage_row(row: dict[str, str]) -> str:
    return (
        f"{row['comparison']} | "
        f"{row['vessel']} | "
        f"{row['task']} | "
        f"{row['tools']} | "
        f"{row['tokens']} | "
        f"{row['cost']} | "
        f"{row['duration']} | "
        f"{row['attempt_artifact']}"
    )


def _task_outcome_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    rows = _task_outcome_rows(
        scorecard,
        task_attempt_scorecard,
        vessel_name,
        task_id,
    )
    include_reason = _include_outcome_reason(rows)
    lines = [
        "",
        "Benchmark task outcomes by vessel:",
        (
            "comparison | vessel | task | result | reason | attempt_artifact"
            if include_reason
            else "comparison | vessel | task | result | attempt_artifact"
        ),
    ]
    lines.extend(_task_outcome_row(row, include_reason=include_reason) for row in rows)
    return lines


def _task_outcome_markdown_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    rows = _task_outcome_rows(
        scorecard,
        task_attempt_scorecard,
        vessel_name,
        task_id,
    )
    include_reason = _include_outcome_reason(rows)
    lines = [
        "",
        "## Benchmark task outcomes by vessel",
        "",
        (
            "| Comparison | Vessel | Task | Result | Reason | Attempt artifact |"
            if include_reason
            else "| Comparison | Vessel | Task | Result | Attempt artifact |"
        ),
        "| --- | --- | --- | --- | --- | --- |"
        if include_reason
        else "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {_task_outcome_row(row, include_reason=include_reason)} |" for row in rows
    )
    return lines


def _task_outcome_rows(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    vessel_name: str | None,
    filter_task_id: str | None,
) -> list[dict[str, str]]:
    attempts_by_vessel = _attempt_artifacts_by_vessel(task_attempt_scorecard)
    rows = []
    for comparison, vessel in _filtered_vessels(scorecard, vessel_name, filter_task_id):
        task_results = _task_results(vessel)
        diagnostics = _task_diagnostics_by_task(vessel)
        if not task_results:
            rows.append(
                {
                    "comparison": str(comparison["name"]),
                    "vessel": str(vessel["name"]),
                    "task": "-",
                    "result": str(vessel["status"]),
                    "reason": "-",
                    "attempt_artifact": _attempt_artifact(
                        attempts_by_vessel,
                        str(comparison["name"]),
                        str(vessel["name"]),
                        None,
                    ),
                }
            )
            continue
        for result_task_id, result in task_results:
            if filter_task_id is not None and result_task_id != filter_task_id:
                continue
            diagnostic = diagnostics.get(result_task_id, {})
            rows.append(
                {
                    "comparison": str(comparison["name"]),
                    "vessel": str(vessel["name"]),
                    "task": result_task_id,
                    "result": result,
                    "reason": str(diagnostic.get("reason", "-")),
                    "attempt_artifact": _attempt_artifact(
                        attempts_by_vessel,
                        str(comparison["name"]),
                        str(vessel["name"]),
                        result_task_id,
                    ),
                }
            )
    return rows


def _task_results(vessel: dict[str, Any]) -> list[tuple[str, str]]:
    resolved = [
        (str(task_id), "resolved") for task_id in vessel.get("resolved_ids", [])
    ]
    unresolved = [
        (str(task_id), "unresolved") for task_id in vessel.get("unresolved_ids", [])
    ]
    return resolved + unresolved


def _task_diagnostics_by_task(vessel: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diagnostics = vessel.get("task_diagnostics", [])
    if not isinstance(diagnostics, list):
        return {}
    return {
        str(diagnostic["task"]): diagnostic
        for diagnostic in diagnostics
        if isinstance(diagnostic, dict) and isinstance(diagnostic.get("task"), str)
    }


def _include_outcome_reason(rows: list[dict[str, str]]) -> bool:
    return any(row.get("reason") not in {None, "-"} for row in rows)


def _task_outcome_row(row: dict[str, str], *, include_reason: bool = False) -> str:
    reason = f"{row['reason']} | " if include_reason else ""
    return (
        f"{row['comparison']} | "
        f"{row['vessel']} | "
        f"{row['task']} | "
        f"{row['result']} | "
        f"{reason}"
        f"{row['attempt_artifact']}"
    )


def _artifact_drilldown_lines(
    logbook_dir: Path,
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    grading_collection: dict[str, Any] | None,
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "Benchmark artifacts by vessel:",
        "comparison | vessel | artifact | path",
    ]
    lines.extend(
        _artifact_drilldown_row(row)
        for row in _artifact_drilldown_rows(
            logbook_dir,
            scorecard,
            task_attempt_scorecard,
            grading_collection,
            vessel_name,
            task_id,
        )
    )
    return lines


def _artifact_drilldown_markdown_lines(
    logbook_dir: Path,
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    grading_collection: dict[str, Any] | None,
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "## Benchmark artifacts by vessel",
        "",
        "| Comparison | Vessel | Artifact | Path |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {_artifact_drilldown_row(row)} |"
        for row in _artifact_drilldown_rows(
            logbook_dir,
            scorecard,
            task_attempt_scorecard,
            grading_collection,
            vessel_name,
            task_id,
        )
    )
    return lines


def _artifact_drilldown_rows(
    logbook_dir: Path,
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    grading_collection: dict[str, Any] | None,
    vessel_name: str | None,
    task_id: str | None,
) -> list[dict[str, str]]:
    attempts_by_vessel = _attempt_artifacts_by_vessel(task_attempt_scorecard)
    grading_by_vessel = _grading_artifacts_by_vessel(grading_collection)
    rows = []
    for comparison, vessel in _filtered_vessels(scorecard, vessel_name, task_id):
        filtered_vessel_name = str(vessel["name"])
        comparison_name = str(comparison["name"])
        grading_artifacts = grading_by_vessel.get(filtered_vessel_name, {})
        rows.extend(
            _artifact_rows(
                comparison_name=comparison_name,
                vessel_name=filtered_vessel_name,
                artifacts={
                    "preflight": str(
                        vessel.get(
                            "preflight_artifact_path",
                            "- (recorded baseline; preflight not run)",
                        )
                    ),
                    "attempts": _attempt_artifact(
                        attempts_by_vessel,
                        comparison_name,
                        filtered_vessel_name,
                        task_id,
                    ),
                    "candidate_patches": _candidate_patches_artifact(
                        logbook_dir,
                        scorecard,
                        filtered_vessel_name,
                    ),
                    "grading_report": _grading_report_artifact(
                        logbook_dir,
                        scorecard,
                        filtered_vessel_name,
                        grading_by_vessel,
                    ),
                    "native_report": grading_artifacts.get("native_report", "-"),
                },
            )
        )
    return rows


def _artifact_drilldown_row(row: dict[str, str]) -> str:
    return f"{row['comparison']} | {row['vessel']} | {row['artifact']} | {row['path']}"


def _artifact_rows(
    *,
    comparison_name: str,
    vessel_name: str,
    artifacts: dict[str, str],
) -> list[dict[str, str]]:
    return [
        {
            "comparison": comparison_name,
            "vessel": vessel_name,
            "artifact": artifact,
            "path": path,
        }
        for artifact, path in artifacts.items()
    ]


def _attempt_artifacts_by_vessel(
    scorecard: dict[str, Any],
) -> dict[tuple[str, str], list[str]]:
    return {
        (str(comparison["name"]), str(vessel["name"])): [
            str(path) for path in vessel["artifact_paths"]
        ]
        for comparison in scorecard["comparisons"]
        for vessel in comparison["vessels"]
    }


def _attempt_artifact(
    attempts_by_vessel: dict[tuple[str, str], list[str]],
    comparison_name: str,
    vessel_name: str,
    task_id: str | None,
) -> str:
    artifacts = attempts_by_vessel.get((comparison_name, vessel_name), [])
    if task_id is None:
        return _joined(artifacts)
    matched = [artifact for artifact in artifacts if Path(artifact).stem == task_id]
    return _joined(matched)


def _candidate_patches_artifact(
    logbook_dir: Path,
    scorecard: dict[str, Any],
    vessel_name: str,
) -> str:
    return str(
        candidate_patches_path(
            logbook_dir=logbook_dir,
            handoff=_artifact_handoff(scorecard),
            vessel_name=vessel_name,
        )
    )


def _grading_report_artifact(
    logbook_dir: Path,
    scorecard: dict[str, Any],
    vessel_name: str,
    grading_by_vessel: dict[str, dict[str, str]],
) -> str:
    grading_report = grading_by_vessel.get(vessel_name, {}).get("grading_report")
    if grading_report:
        return grading_report
    return str(
        grading_report_path(
            logbook_dir=logbook_dir,
            handoff=_artifact_handoff(scorecard),
            vessel_name=vessel_name,
        )
    )


def _artifact_handoff(scorecard: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter": {
            "kind": str(scorecard["adapter"]["kind"]),
        },
    }


def _grading_artifacts_by_vessel(
    grading_collection: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    if grading_collection is None:
        return {}
    return {
        str(vessel["name"]): {
            "native_report": str(vessel.get("native_report_path", "-")),
            "grading_report": str(vessel.get("grading_report_path", "-")),
        }
        for comparison in grading_collection.get("comparisons", [])
        for vessel in comparison.get("vessels", [])
    }


def _joined(values: list[str]) -> str:
    if not values:
        return "-"
    return ", ".join(values)


def _tool_counts(value: dict[str, int]) -> str:
    if not value:
        return "-"
    return ", ".join(f"{tool}:{count}" for tool, count in value.items())


def _harnesses(vessel: dict[str, Any]) -> str:
    harnesses = vessel.get("harnesses")
    if not isinstance(harnesses, list) or not harnesses:
        return "-"
    return ", ".join(str(harness) for harness in harnesses)


def _cost(value: float) -> str:
    return f"{float(value):.6f}"


def _rate(value: float) -> str:
    return f"{float(value):.3f}"


def _duration(value: float) -> str:
    return f"{float(value):.3f}s"
