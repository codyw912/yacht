from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    TASK_ATTEMPT_SCORECARD_SCHEMA,
    SchemaValidationError,
    validate_task_attempt_document,
    validate_task_attempt_scorecard_document,
)
from yacht.reports.statistics import wilson_interval
from yacht.workflows.provenance import collapse_provenance


TASK_ATTEMPT_SCORECARD_PATH = Path("task-attempt-scorecard.json")


def write_task_attempt_scorecard(logbook_dir: Path) -> dict[str, Any]:
    attempts = _load_task_attempts(logbook_dir)
    scorecard = _build_scorecard(attempts)
    validate_task_attempt_scorecard_document(scorecard)
    _write_json(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH, scorecard)
    return scorecard


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
        raise ConfigError(
            f"task attempt artifact is not valid JSON: {error}"
        ) from error
    if not isinstance(attempt, dict):
        raise ConfigError("task attempt artifact must be a JSON object")
    try:
        validate_task_attempt_document(attempt)
    except SchemaValidationError as error:
        raise ConfigError(f"task attempt artifact is invalid: {error}") from error
    attempt["artifact_path"] = str(path)
    return attempt


def _build_scorecard(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = _comparison_scores(attempts)
    return {
        "schema": TASK_ATTEMPT_SCORECARD_SCHEMA,
        "regatta": str(attempts[0]["regatta"]),
        "course": str(attempts[0]["course"]),
        "status": _scorecard_status(comparisons),
        "summary": _top_level_summary(comparisons),
        "comparisons": comparisons,
    }


def _comparison_scores(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _comparison_score(comparison_name, comparison_attempts)
        for comparison_name, comparison_attempts in _group_by(
            attempts,
            "comparison",
        ).items()
    ]


def _comparison_score(
    comparison_name: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    vessels = [
        _vessel_score(vessel_name, vessel_attempts)
        for vessel_name, vessel_attempts in _group_by(attempts, "vessel").items()
    ]
    return {
        "name": comparison_name,
        "summary": _summary(vessels),
        "vessels": vessels,
    }


def _vessel_score(vessel_name: str, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    completed_attempts = sum(
        1 for attempt in attempts if attempt["status"] == "completed"
    )
    failed_attempts = len(attempts) - completed_attempts
    total_duration = sum(
        float(attempt["metrics"]["duration_seconds"]) for attempt in attempts
    )
    provenance = collapse_provenance(
        [attempt.get("provenance") for attempt in attempts]
    )
    payload = {
        "name": vessel_name,
        "status": "failed" if failed_attempts else "measured",
        "task_attempts": len(attempts),
        "completed_attempts": completed_attempts,
        "failed_attempts": failed_attempts,
        "success_rate": completed_attempts / len(attempts),
        "harnesses": _harnesses(attempts),
        "tool_call_count": sum(
            len(attempt["agent"]["tool_calls"]) for attempt in attempts
        ),
        "tool_call_counts": _tool_call_counts(attempts),
        "total_tokens": sum(int(attempt["metrics"]["tokens"]) for attempt in attempts),
        "total_cost": round(sum(_attempt_cost(attempt) for attempt in attempts), 6),
        "total_duration_seconds": round(total_duration, 3),
        "artifact_paths": [str(attempt["artifact_path"]) for attempt in attempts],
    }
    if provenance is not None:
        payload["provenance"] = provenance
    tool_invocations = _tool_invocations(attempts)
    if tool_invocations:
        payload["tool_invocations"] = tool_invocations
    usage_sources = sorted(
        {
            str(attempt["metrics"]["usage_source"])
            for attempt in attempts
            if "usage_source" in attempt["metrics"]
        }
    )
    if usage_sources:
        payload["usage_sources"] = usage_sources
    payload["cost_sources"] = sorted(
        {_attempt_cost_source(attempt) for attempt in attempts}
    )
    return payload


def _tool_invocations(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Delivery rates for the vessel's expected tools. Only attempts with
    preserved trajectory evidence count toward the denominators — an
    unmeasured attempt says nothing about whether the tool fired."""
    expectations: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        for expectation in attempt.get("tool_expectations", ()):
            expectations.setdefault(str(expectation["tool"]), expectation)
    measured = [
        attempt for attempt in attempts if "tool_call_evidence" in attempt["agent"]
    ]
    entries = []
    for tool, expectation in expectations.items():
        expected_calls = [str(call) for call in expectation["expected_calls"]]
        entry: dict[str, Any] = {
            "tool": tool,
            "kind": str(expectation["kind"]),
            "expected_calls": expected_calls,
            "attempts": len(attempts),
            "measured_attempts": len(measured),
        }
        if not measured:
            entry["status"] = "unmeasured"
            entries.append(entry)
            continue
        invoked = [attempt for attempt in measured if _invoked(attempt, expected_calls)]
        completed = [
            attempt for attempt in measured if attempt["status"] == "completed"
        ]
        invoked_completed = [
            attempt for attempt in completed if _invoked(attempt, expected_calls)
        ]
        entry.update(
            {
                "status": "measured",
                "invoked_attempts": len(invoked),
                "invocation_rate": len(invoked) / len(measured),
                "invocation_interval": wilson_interval(len(invoked), len(measured)),
            }
        )
        if completed:
            entry.update(
                {
                    "completed_attempts": len(completed),
                    "invoked_completed_attempts": len(invoked_completed),
                    "completed_invocation_rate": (
                        len(invoked_completed) / len(completed)
                    ),
                    "completed_invocation_interval": wilson_interval(
                        len(invoked_completed),
                        len(completed),
                    ),
                }
            )
        entries.append(entry)
    return entries


def _invoked(attempt: dict[str, Any], expected_calls: list[str]) -> bool:
    observed = set(attempt["agent"]["tool_calls"])
    return any(call in observed for call in expected_calls)


def _top_level_summary(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_comparisons": len(comparisons),
        **_summary(
            [vessel for comparison in comparisons for vessel in comparison["vessels"]]
        ),
    }


def _summary(vessels: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_vessels": len(vessels),
        "total_attempts": sum(int(vessel["task_attempts"]) for vessel in vessels),
        "completed_attempts": sum(
            int(vessel["completed_attempts"]) for vessel in vessels
        ),
        "failed_attempts": sum(int(vessel["failed_attempts"]) for vessel in vessels),
        "total_tool_calls": sum(int(vessel["tool_call_count"]) for vessel in vessels),
        "tool_call_counts": _summary_tool_call_counts(vessels),
        "total_tokens": sum(int(vessel["total_tokens"]) for vessel in vessels),
        "total_cost": round(sum(float(vessel["total_cost"]) for vessel in vessels), 6),
        "total_duration_seconds": round(
            sum(float(vessel["total_duration_seconds"]) for vessel in vessels),
            3,
        ),
    }


def _scorecard_status(comparisons: list[dict[str, Any]]) -> str:
    failed_attempts = sum(
        int(comparison["summary"]["failed_attempts"]) for comparison in comparisons
    )
    return "partial" if failed_attempts else "complete"


def _group_by(
    attempts: list[dict[str, Any]],
    key: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        grouped.setdefault(str(attempt[key]), []).append(attempt)
    return grouped


def _tool_call_counts(attempts: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        for tool_call in attempt["agent"]["tool_calls"]:
            counts[str(tool_call)] = counts.get(str(tool_call), 0) + 1
    return dict(sorted(counts.items()))


def _harnesses(attempts: list[dict[str, Any]]) -> list[str]:
    harnesses = {
        str(attempt["runtime_context"]["harness"])
        for attempt in attempts
        if attempt["runtime_context"].get("harness") is not None
    }
    return sorted(harnesses)


def _summary_tool_call_counts(vessels: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for vessel in vessels:
        for tool_call, count in vessel["tool_call_counts"].items():
            counts[str(tool_call)] = counts.get(str(tool_call), 0) + int(count)
    return dict(sorted(counts.items()))


# Built-in adapters report cost.total; the ADR 0017 mapping path reports
# cost.total_usd, which is the name the harness-evidence schema requires.
# Reading only one silently zeroes the other's spend.
COST_TOTAL_KEYS = ("total", "total_usd")


def _attempt_cost(attempt: dict[str, Any]) -> float:
    agent = attempt.get("agent")
    if not isinstance(agent, dict):
        return 0.0
    machine_evidence = agent.get("machine_evidence")
    if not isinstance(machine_evidence, dict):
        return 0.0
    cost = machine_evidence.get("cost")
    if not isinstance(cost, dict):
        return 0.0
    for key in COST_TOTAL_KEYS:
        total = cost.get(key)
        if (
            isinstance(total, int | float)
            and not isinstance(total, bool)
            and total >= 0
        ):
            return float(total)
    return 0.0


def _attempt_cost_source(attempt: dict[str, Any]) -> str:
    """Whether the harness reported a cost at all.

    Tokens already carry usage_source; without the same for cost, a
    total of 0.0 is indistinguishable from a harness that said nothing.
    """
    agent = attempt.get("agent")
    if not isinstance(agent, dict):
        return "unreported"
    machine_evidence = agent.get("machine_evidence")
    if not isinstance(machine_evidence, dict):
        return "unreported"
    cost = machine_evidence.get("cost")
    if not isinstance(cost, dict):
        return "unreported"
    for key in COST_TOTAL_KEYS:
        total = cost.get(key)
        if (
            isinstance(total, int | float)
            and not isinstance(total, bool)
            and total >= 0
        ):
            return "reported"
    return "unreported"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
