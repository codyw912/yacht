from __future__ import annotations

from typing import Any


def render_real_benchmark_eval_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Real benchmark eval: {summary['regatta']} / {summary['course']}",
        f"Status: {summary['status']}",
    ]
    agent = summary.get("agent")
    if isinstance(agent, str) and agent:
        lines.append(f"Agent: {agent}")
    lines.extend(_stage_lines(summary))
    lines.extend(_usage_lines(summary.get("task_attempt_scorecard")))
    lines.extend(_scorecard_lines(summary.get("scorecard")))
    lines.extend(_blocked_lines(summary))
    lines.extend(_artifact_lines(summary))
    lines.extend(_next_step_lines(summary.get("next_steps")))
    return "\n".join(lines) + "\n"


def render_real_benchmark_repetitions_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Real benchmark repetitions: {summary['regatta']} / {summary['course']}",
        f"Status: {summary['status']}",
    ]
    agent = summary.get("agent")
    if isinstance(agent, str) and agent:
        lines.append(f"Agent: {agent}")
    run_summary = summary.get("summary")
    if isinstance(run_summary, dict):
        lines.append(
            "Runs: "
            f"{run_summary.get('repetitions', 0)} | "
            f"completed={run_summary.get('completed_runs', 0)} | "
            f"failed={run_summary.get('failed_runs', 0)} | "
            f"aggregated={run_summary.get('aggregate_logbooks', 0)}"
        )
    lines.extend(_aggregate_delta_lines(summary.get("aggregate_summary")))
    lines.extend(_artifact_lines(summary))
    lines.extend(_next_step_lines(summary.get("next_steps")))
    return "\n".join(lines) + "\n"


def _stage_lines(summary: dict[str, Any]) -> list[str]:
    stage_parts = []
    for label, key in (
        ("preflight", "preflight_evidence_report"),
        ("attempts", "attempts"),
        ("launch", "benchmark_launch"),
        ("grading", "grading_collection"),
        ("scorecard", "scorecard"),
    ):
        payload = summary.get(key)
        if isinstance(payload, dict):
            stage_parts.append(f"{label}={payload.get('status', 'unknown')}")
    if not stage_parts:
        return []
    return ["Stages: " + " | ".join(stage_parts)]


def _usage_lines(scorecard: Any) -> list[str]:
    if not isinstance(scorecard, dict):
        return []
    usage = scorecard.get("summary")
    if not isinstance(usage, dict):
        return []
    return [
        "Usage: "
        f"attempts={usage.get('total_attempts', 0)} | "
        f"failed={usage.get('failed_attempts', 0)} | "
        f"tokens={usage.get('total_tokens', 0)} | "
        f"cost={_cost(usage.get('total_cost', 0.0))} | "
        f"duration={_duration(usage.get('total_duration_seconds', 0.0))} | "
        f"tool_calls={usage.get('total_distinct_tool_uses', 0)}"
    ]


def _scorecard_lines(scorecard: Any) -> list[str]:
    if not isinstance(scorecard, dict):
        return []
    comparisons = scorecard.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        return []
    lines = [
        "",
        "Benchmark outcomes:",
        "comparison | baseline | challenger | resolved_delta | rate_delta | "
        "measured | missing",
    ]
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        delta = comparison.get("delta")
        vessels = comparison.get("vessels")
        summary = comparison.get("summary")
        if not isinstance(delta, dict) or not isinstance(summary, dict):
            continue
        baseline = delta.get("baseline_vessel", _vessel_name(vessels, 0))
        challenger = delta.get("challenger_vessel", _vessel_name(vessels, 1))
        lines.append(
            f"{comparison.get('name', 'unknown')} | "
            f"{baseline} | "
            f"{challenger} | "
            f"{_signed_int(delta.get('resolved_instances_delta', 0))} | "
            f"{_signed_rate(delta.get('resolution_rate_delta', 0.0))} | "
            f"{summary.get('measured_vessels', 0)} | "
            f"{summary.get('missing_result_vessels', 0)}"
        )
    return lines


def _aggregate_delta_lines(aggregate_summary: Any) -> list[str]:
    if not isinstance(aggregate_summary, dict):
        return []
    comparisons = aggregate_summary.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        return []
    lines = [
        "",
        "Aggregate deltas:",
        "comparison | baseline | challenger | resolved_delta | rate_delta | "
        "tokens_delta | cost_delta | duration_delta | distinct_tool_uses_delta",
    ]
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        delta = comparison.get("delta")
        if not isinstance(delta, dict):
            continue
        baseline = comparison.get(
            "baseline",
            delta.get("baseline_vessel", "baseline"),
        )
        challenger = comparison.get(
            "challenger",
            delta.get("challenger_vessel", "challenger"),
        )
        lines.append(
            f"{comparison.get('name', 'unknown')} | "
            f"{baseline} | "
            f"{challenger} | "
            f"{_signed_int(delta.get('resolved_instances_delta', 0))} | "
            f"{_signed_rate(delta.get('resolution_rate_delta', 0.0))} | "
            f"{_signed_int(delta.get('tokens_delta', 0))} | "
            f"{_signed_cost(delta.get('cost_delta', 0.0))} | "
            f"{_signed_duration(delta.get('duration_seconds_delta', 0.0))} | "
            f"{_signed_int(delta.get('distinct_tool_uses_delta', 0))}"
        )
    return lines


def _blocked_lines(summary: dict[str, Any]) -> list[str]:
    lines = []
    if "failed_stage" in summary:
        lines.append(f"Failed stage: {summary['failed_stage']}")
    if "error" in summary:
        lines.append(f"Error: {summary['error']}")
    blocked_preflight = summary.get("blocked_preflight")
    if isinstance(blocked_preflight, dict):
        lines.append(
            "Blocked preflight: "
            f"{blocked_preflight.get('blocked_vessel_count', 0)}/"
            f"{blocked_preflight.get('total_vessel_count', 0)} vessel(s)"
        )
    skipped = summary.get("skipped")
    if isinstance(skipped, list) and skipped:
        lines.append("Skipped: " + ", ".join(str(item) for item in skipped))
    return lines


def _artifact_lines(summary: dict[str, Any]) -> list[str]:
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    parts = []
    for key in (
        "logbook",
        "real_benchmark_eval",
        "real_benchmark_repetitions",
        "benchmark_scorecard",
        "benchmark_aggregate",
        "benchmark_report_markdown",
    ):
        value = artifacts.get(key)
        if isinstance(value, str):
            parts.append(f"{key}={value}")
    if not parts:
        return []
    return ["", "Artifacts: " + " | ".join(parts)]


def _next_step_lines(steps: Any) -> list[str]:
    if not isinstance(steps, list) or not steps:
        return []
    lines = ["", "Next steps:"]
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        lines.append(f"{index}. {step.get('label', 'Next step')}")
        command = step.get("command_preview")
        if isinstance(command, str):
            lines.append(f"   command: {command}")
        reason = step.get("reason")
        if isinstance(reason, str):
            lines.append(f"   reason: {reason}")
    return lines


def _vessel_name(vessels: Any, index: int) -> str:
    if isinstance(vessels, list) and len(vessels) > index:
        vessel = vessels[index]
        if isinstance(vessel, dict) and isinstance(vessel.get("name"), str):
            return vessel["name"]
    return "unknown"


def _signed_int(value: Any) -> str:
    return f"{int(value):+d}"


def _signed_rate(value: Any) -> str:
    return f"{float(value):+.3f}"


def _signed_cost(value: Any) -> str:
    return f"{float(value):+.6f}"


def _signed_duration(value: Any) -> str:
    return f"{float(value):+.3f}s"


def _cost(value: Any) -> str:
    return f"{float(value):.6f}"


def _duration(value: Any) -> str:
    return f"{float(value):.3f}s"
