from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.benchmark_grading_collection import BENCHMARK_GRADING_COLLECTION_PATH
from yacht.benchmark_launch import BENCHMARK_LAUNCH_RESULT_PATH
from yacht.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.regatta import ConfigError
from yacht.schemas import (
    SchemaValidationError,
    validate_benchmark_scorecard_document,
    validate_task_attempt_document,
    validate_task_attempt_scorecard_document,
)
from yacht.swebench_artifacts import candidate_patches_path, grading_report_path
from yacht.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


def render_benchmark_report(
    logbook_dir: Path,
    output_format: str = "text",
    *,
    vessel_name: str | None = None,
    task_id: str | None = None,
) -> str:
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
    _validate_filters(scorecard, vessel_name, task_id)
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
        "Comparisons: "
        f"{summary['total_comparisons']} | "
        f"Vessels: {summary['total_vessels']} | "
        f"Measured: {summary['measured_vessels']} | "
        f"Missing: {summary['missing_result_vessels']}",
        _usage_summary_line(task_attempt_scorecard),
        _artifact_line(logbook_dir),
    ]
    lines.extend(_filter_lines(vessel_name, task_id))
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
        f"- Comparisons: {summary['total_comparisons']}",
        f"- Vessels: {summary['total_vessels']}",
        f"- Measured: {summary['measured_vessels']}",
        f"- Missing: {summary['missing_result_vessels']}",
        *_usage_summary_markdown_lines(task_attempt_scorecard),
        *_filter_markdown_lines(vessel_name, task_id),
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
    if vessel_name is not None and task_id is not None and not any(
        _matches_filters(vessel, vessel_name, task_id)
        for _, vessel in _vessels(scorecard)
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
        f"{vessel['preflight_reason']}"
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
        "comparison | vessel | attempts | failed | tools | tokens | cost | duration",
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
        "| Comparison | Vessel | Attempts | Failed | Tools | Tokens | Cost | "
        "Duration |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
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
        f"{vessel['task_attempts']} | "
        f"{vessel['failed_attempts']} | "
        f"{_tool_counts(vessel['tool_call_counts'])} | "
        f"{vessel['total_tokens']} | "
        f"{_cost(vessel['total_cost'])} | "
        f"{_duration(vessel['total_duration_seconds'])}"
    )


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
    lines = [
        "",
        "Benchmark task outcomes by vessel:",
        "comparison | vessel | task | result | attempt_artifact",
    ]
    lines.extend(
        _task_outcome_row(row)
        for row in _task_outcome_rows(
            scorecard,
            task_attempt_scorecard,
            vessel_name,
            task_id,
        )
    )
    return lines


def _task_outcome_markdown_lines(
    scorecard: dict[str, Any],
    task_attempt_scorecard: dict[str, Any],
    vessel_name: str | None,
    task_id: str | None,
) -> list[str]:
    lines = [
        "",
        "## Benchmark task outcomes by vessel",
        "",
        "| Comparison | Vessel | Task | Result | Attempt artifact |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {_task_outcome_row(row)} |"
        for row in _task_outcome_rows(
            scorecard,
            task_attempt_scorecard,
            vessel_name,
            task_id,
        )
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
        if not task_results:
            rows.append(
                {
                    "comparison": str(comparison["name"]),
                    "vessel": str(vessel["name"]),
                    "task": "-",
                    "result": str(vessel["status"]),
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
            rows.append(
                {
                    "comparison": str(comparison["name"]),
                    "vessel": str(vessel["name"]),
                    "task": result_task_id,
                    "result": result,
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


def _task_outcome_row(row: dict[str, str]) -> str:
    return (
        f"{row['comparison']} | "
        f"{row['vessel']} | "
        f"{row['task']} | "
        f"{row['result']} | "
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
                    "preflight": str(vessel["preflight_artifact_path"]),
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
    return (
        f"{row['comparison']} | "
        f"{row['vessel']} | "
        f"{row['artifact']} | "
        f"{row['path']}"
    )


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
    matched = [
        artifact
        for artifact in artifacts
        if Path(artifact).stem == task_id
    ]
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


def _cost(value: float) -> str:
    return f"{float(value):.6f}"


def _rate(value: float) -> str:
    return f"{float(value):.3f}"


def _duration(value: float) -> str:
    return f"{float(value):.3f}s"
