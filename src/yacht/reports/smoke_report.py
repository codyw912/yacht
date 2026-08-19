from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_smoke_readiness_report_document,
    validate_task_attempt_scorecard_document,
)
from yacht.logbook.index import LogbookSnapshot, LogbookState, require_logbook


SMOKE_REPORT_PATH = Path("smoke-report.txt")


_REPORT_ARTIFACT_PATHS = {
    "smoke_report": SMOKE_REPORT_PATH,
    "smoke_readiness_report": Path("smoke-readiness-report.json"),
    "task_attempt_scorecard": Path("task-attempt-scorecard.json"),
}


def write_smoke_report(logbook_dir: Path) -> str:
    report = render_smoke_report(logbook_dir)
    path = logbook_dir / SMOKE_REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return report


def render_smoke_report(logbook_dir: Path, output_format: str = "text") -> str:
    snapshot = require_logbook(logbook_dir)
    readiness = _load_readiness(snapshot)
    scorecard = _load_scorecard(snapshot)
    if output_format == "markdown":
        return _render_markdown(snapshot, readiness, scorecard)
    return _render_text(snapshot, readiness, scorecard)


def _load_readiness(snapshot: LogbookSnapshot) -> dict[str, Any]:
    path = _require_artifact(
        snapshot,
        "smoke_readiness_report",
        "smoke readiness report",
    )
    readiness = _load_json_object(path, "smoke readiness report artifact")
    try:
        validate_smoke_readiness_report_document(readiness)
    except SchemaValidationError as error:
        raise ConfigError(
            f"smoke readiness report artifact is invalid: {error}"
        ) from error
    return readiness


def _load_scorecard(snapshot: LogbookSnapshot) -> dict[str, Any]:
    path = _require_artifact(
        snapshot,
        "task_attempt_scorecard",
        "task attempt scorecard",
    )
    scorecard = _load_json_object(path, "task attempt scorecard artifact")
    try:
        validate_task_attempt_scorecard_document(scorecard)
    except SchemaValidationError as error:
        raise ConfigError(
            f"task attempt scorecard artifact is invalid: {error}"
        ) from error
    return scorecard


def _require_artifact(
    snapshot: LogbookSnapshot,
    name: str,
    label: str,
) -> Path:
    artifact = snapshot.artifact(name)
    if artifact is None:
        raise ConfigError(f"{label} artifact is not indexed")
    if not artifact.file_present:
        raise ConfigError(f"{label} artifact not found: {artifact.path}")
    return artifact.path


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return payload


def _render_text(
    snapshot: LogbookSnapshot,
    readiness: dict[str, Any],
    scorecard: dict[str, Any],
) -> str:
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
        f"Distinct tools: {scorecard_summary['total_distinct_tool_uses']} | "
        f"Tokens: {scorecard_summary['total_tokens']} | "
        f"Cost: {_cost(scorecard_summary['total_cost'])}",
        _artifact_line(snapshot),
        "",
        "comparison | vessel | status | preflight | attempts | tools | expected | "
        "missing | tokens | cost | details",
    ]
    lines.extend(
        _vessel_row(comparison, vessel, scorecard)
        for comparison, vessel in _vessels(readiness)
    )
    return "\n".join(lines) + "\n"


def _render_markdown(
    snapshot: LogbookSnapshot,
    readiness: dict[str, Any],
    scorecard: dict[str, Any],
) -> str:
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
        f"- Distinct tools: {scorecard_summary['total_distinct_tool_uses']}",
        f"- Tokens: {scorecard_summary['total_tokens']}",
        f"- Cost: {_cost(scorecard_summary['total_cost'])}",
        f"- Logbook: `{snapshot.logbook}`",
        f"- Smoke report: `{_artifact_location(snapshot, 'smoke_report')}`",
        f"- Smoke readiness report: "
        f"`{_artifact_location(snapshot, 'smoke_readiness_report')}`",
        f"- Task attempt scorecard: "
        f"`{_artifact_location(snapshot, 'task_attempt_scorecard')}`",
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


def _artifact_line(snapshot: LogbookSnapshot) -> str:
    return (
        f"Artifacts: logbook={snapshot.logbook} | "
        f"readiness={_artifact_location(snapshot, 'smoke_readiness_report')} | "
        f"scorecard={_artifact_location(snapshot, 'task_attempt_scorecard')} | "
        f"report={_artifact_location(snapshot, 'smoke_report')}"
    )


def _artifact_location(snapshot: LogbookSnapshot, name: str) -> str:
    artifact = snapshot.artifact(name)
    if (
        artifact is not None
        and snapshot.state is not LogbookState.LEGACY_SCORECARD_ONLY
    ):
        return str(artifact.path)
    default_path = _REPORT_ARTIFACT_PATHS.get(name)
    if default_path is not None:
        return str(snapshot.logbook / default_path)
    return "not indexed"


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
        f"{_tool_counts(readiness_vessel['attempts_by_tool'])} | "
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
        f"task attempt scorecard is missing vessel {comparison_name}/{vessel_name}"
    )


def _tool_counts(value: dict[str, int]) -> str:
    if not value:
        return "-"
    return ", ".join(f"{tool}:{count}" for tool, count in value.items())


def _tool_list(value: list[str]) -> str:
    return ", ".join(value) if value else "-"


def _cost(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6f}"


def _details(vessel: dict[str, Any]) -> str:
    if not vessel["reasons"]:
        return "-"
    return "; ".join(str(reason) for reason in vessel["reasons"])
