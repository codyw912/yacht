from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.regatta import ConfigError
from yacht.schemas import (
    SMOKE_READINESS_REPORT_SCHEMA,
    SchemaValidationError,
    validate_preflight_document,
    validate_smoke_readiness_report_document,
    validate_task_attempt_document,
    validate_task_attempt_scorecard_document,
)
from yacht.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


SMOKE_READINESS_REPORT_PATH = Path("smoke-readiness-report.json")


def write_smoke_readiness_report(logbook_dir: Path) -> dict[str, Any]:
    report = build_smoke_readiness_report(logbook_dir)
    _write_json(logbook_dir / SMOKE_READINESS_REPORT_PATH, report)
    return report


def build_smoke_readiness_report(logbook_dir: Path) -> dict[str, Any]:
    scorecard = _load_scorecard(logbook_dir)
    comparisons = [
        _comparison_readiness(logbook_dir, comparison)
        for comparison in scorecard["comparisons"]
    ]
    comparisons = _require_agent_prompt_evidence(comparisons)
    summary = _summary(comparisons)
    report = {
        "schema": SMOKE_READINESS_REPORT_SCHEMA,
        "regatta": scorecard["regatta"],
        "course": scorecard["course"],
        "status": "blocked" if summary["blocked_vessels"] else "ready",
        "summary": summary,
        "comparisons": comparisons,
    }
    validate_smoke_readiness_report_document(report)
    return report


def _load_scorecard(logbook_dir: Path) -> dict[str, Any]:
    scorecard_path = logbook_dir / TASK_ATTEMPT_SCORECARD_PATH
    if not scorecard_path.exists():
        raise ConfigError(f"task attempt scorecard artifact not found: {scorecard_path}")
    scorecard = _load_json_object(scorecard_path, "task attempt scorecard artifact")
    try:
        validate_task_attempt_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"task attempt scorecard artifact is invalid: {error}"
        ) from error
    return scorecard


def _comparison_readiness(
    logbook_dir: Path,
    comparison: dict[str, Any],
) -> dict[str, Any]:
    vessels = [
        _vessel_readiness(logbook_dir, str(comparison["name"]), vessel)
        for vessel in comparison["vessels"]
    ]
    return {
        "name": comparison["name"],
        "status": _aggregate_status(vessels),
        "vessels": vessels,
    }


def _vessel_readiness(
    logbook_dir: Path,
    comparison_name: str,
    scorecard_vessel: dict[str, Any],
) -> dict[str, Any]:
    preflight_path = (
        logbook_dir / "preflight" / comparison_name / f"{scorecard_vessel['name']}.json"
    )
    preflight = _load_preflight(preflight_path)
    artifact_paths = [
        _resolve_logbook_path(logbook_dir, path)
        for path in scorecard_vessel["artifact_paths"]
    ]
    invalid_attempts = [
        str(path) for path in artifact_paths if not _valid_task_attempt(path)
    ]
    tool_call_counts = _tool_call_counts(scorecard_vessel)
    expected_tool_calls = _expected_tool_calls(preflight)
    missing_expected_tool_calls = _missing_expected_tool_calls(
        expected_tool_calls,
        tool_call_counts,
    )
    reasons = _vessel_reasons(
        preflight=preflight,
        scorecard_vessel=scorecard_vessel,
        invalid_attempts=invalid_attempts,
        missing_expected_tool_calls=missing_expected_tool_calls,
    )
    status = _vessel_status(reasons)
    return {
        "name": scorecard_vessel["name"],
        "status": status,
        "preflight_status": _preflight_status(preflight),
        "task_attempt_status": scorecard_vessel["status"],
        "preflight_artifact_path": str(preflight_path),
        "task_attempt_artifact_paths": [str(path) for path in artifact_paths],
        "agent_prompt_checks": _agent_prompt_check_counts(preflight),
        "tool_call_counts": tool_call_counts,
        "expected_tool_calls": expected_tool_calls,
        "missing_expected_tool_calls": missing_expected_tool_calls,
        "reasons": reasons,
    }


def _load_preflight(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        preflight = _load_json_object(path, "preflight artifact")
    except ConfigError:
        return {"status": "invalid", "checks": []}
    try:
        validate_preflight_document(preflight)
    except SchemaValidationError:
        return {"status": "invalid", "checks": []}
    return preflight


def _valid_task_attempt(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        attempt = _load_json_object(path, "task attempt artifact")
    except ConfigError:
        return False
    try:
        validate_task_attempt_document(attempt)
    except SchemaValidationError:
        return False
    return True


def _vessel_reasons(
    *,
    preflight: dict[str, Any] | None,
    scorecard_vessel: dict[str, Any],
    invalid_attempts: list[str],
    missing_expected_tool_calls: list[str],
) -> list[str]:
    reasons: list[str] = []
    if preflight is None:
        reasons.append("missing-preflight")
    elif preflight.get("status") == "invalid":
        reasons.append("preflight-invalid")
    elif preflight.get("status") != "passed":
        reasons.append("preflight-failed")
    if scorecard_vessel["status"] != "measured":
        reasons.append("task-attempt-failed")
    if invalid_attempts:
        reasons.append("task-attempt-invalid")
    if missing_expected_tool_calls:
        reasons.append("missing-expected-tool-calls")
    return reasons


def _vessel_status(reasons: list[str]) -> str:
    if not reasons:
        return "ready"
    return reasons[0]


def _preflight_status(preflight: dict[str, Any] | None) -> str:
    if preflight is None:
        return "missing"
    return str(preflight["status"])


def _agent_prompt_check_counts(preflight: dict[str, Any] | None) -> dict[str, int]:
    if preflight is None:
        return {"total": 0, "passed": 0}
    checks = [
        check
        for check in preflight.get("checks", [])
        if check.get("kind") == "agent-prompt"
    ]
    return {
        "total": len(checks),
        "passed": sum(1 for check in checks if check.get("status") == "passed"),
    }


def _tool_call_counts(scorecard_vessel: dict[str, Any]) -> dict[str, int]:
    counts = scorecard_vessel.get("tool_call_counts", {})
    if not isinstance(counts, dict):
        return {}
    return {
        str(tool_name): int(count)
        for tool_name, count in sorted(counts.items())
        if isinstance(count, int) and count > 0
    }


def _expected_tool_calls(preflight: dict[str, Any] | None) -> list[str]:
    if preflight is None:
        return []
    expected_tool_calls: list[str] = []
    for check in preflight.get("checks", []):
        if check.get("kind") != "agent-prompt":
            continue
        evidence = check.get("evidence", {})
        if not isinstance(evidence, dict):
            continue
        for tool_call in evidence.get("expected_tool_calls", []):
            if isinstance(tool_call, str) and tool_call not in expected_tool_calls:
                expected_tool_calls.append(tool_call)
    return expected_tool_calls


def _missing_expected_tool_calls(
    expected_tool_calls: list[str],
    tool_call_counts: dict[str, int],
) -> list[str]:
    return [
        tool_call
        for tool_call in expected_tool_calls
        if tool_call_counts.get(tool_call, 0) <= 0
    ]


def _summary(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    vessels = [
        vessel for comparison in comparisons for vessel in comparison["vessels"]
    ]
    passed_agent_prompt_checks = sum(
        int(vessel["agent_prompt_checks"]["passed"]) for vessel in vessels
    )
    blocked_vessels = sum(1 for vessel in vessels if vessel["status"] != "ready")
    return {
        "total_vessels": len(vessels),
        "ready_vessels": len(vessels) - blocked_vessels,
        "blocked_vessels": blocked_vessels,
        "passed_preflight_vessels": sum(
            1 for vessel in vessels if vessel["preflight_status"] == "passed"
        ),
        "completed_task_attempt_vessels": sum(
            1 for vessel in vessels if vessel["task_attempt_status"] == "measured"
        ),
        "passed_agent_prompt_checks": passed_agent_prompt_checks,
    }


def _require_agent_prompt_evidence(
    comparisons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if any(
        vessel["agent_prompt_checks"]["passed"]
        for comparison in comparisons
        for vessel in comparison["vessels"]
    ):
        return comparisons
    return [
        {
            **comparison,
            "status": "blocked",
            "vessels": [
                _mark_missing_agent_prompt_evidence(vessel)
                for vessel in comparison["vessels"]
            ],
        }
        for comparison in comparisons
    ]


def _mark_missing_agent_prompt_evidence(vessel: dict[str, Any]) -> dict[str, Any]:
    if vessel["status"] != "ready":
        return vessel
    return {
        **vessel,
        "status": "missing-agent-prompt-evidence",
        "reasons": [*vessel["reasons"], "missing-agent-prompt-evidence"],
    }


def _aggregate_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "blocked"
    if all(item["status"] == "ready" for item in items):
        return "ready"
    return "blocked"


def _resolve_logbook_path(logbook_dir: Path, path: str) -> Path:
    artifact_path = Path(path)
    if artifact_path.is_absolute():
        return artifact_path
    return logbook_dir / artifact_path


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
