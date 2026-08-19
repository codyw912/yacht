"""Discover logbooks under a root and flatten them into vessel records.

The dashboard renders from disk on every request (ADR 0010): discovery
rescans the root, and records are rebuilt from the scorecard artifacts each
time. A logbook whose artifacts fail to parse or validate is returned as an
entry with an error instead of being silently skipped, so the dashboard can
render it as visibly broken.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_benchmark_scorecard_document,
    validate_task_attempt_scorecard_document,
    validate_smoke_readiness_report_document,
)
from yacht.domain.model import ConfigError
from yacht.logbook.index import (
    RUN_INDEX_PATH,
    LogbookSnapshot,
    LogbookState,
    is_logbook_candidate,
    read_logbook,
)
from yacht.reports.task_attempt_scorecard import normalize_task_attempt_scorecard


@dataclass(frozen=True)
class LogbookEntry:
    logbook: Path
    updated_at: str
    regatta: str | None = None
    course: str | None = None
    status: str | None = None
    outcome: str | None = None
    benchmark_scorecard: dict[str, Any] | None = None
    benchmark_scorecard_path: Path | None = None
    attempt_scorecard: dict[str, Any] | None = None
    missing_artifacts: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class VesselRecord:
    logbook: str
    regatta: str
    course: str
    comparison: str
    vessel: str
    status: str
    provenance: dict[str, Any] | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)


def discover_logbooks(root: Path) -> list[LogbookEntry]:
    if not root.is_dir():
        raise ConfigError(f"dashboard root is not a directory: {root}")
    candidates = [root]
    candidates.extend(
        sorted(child for child in root.iterdir() if _is_readable_dir(child))
    )
    entries = []
    for candidate in candidates:
        if is_logbook_candidate(candidate):
            entries.append(_load_entry(read_logbook(candidate)))
    entries.sort(key=lambda entry: (entry.updated_at, str(entry.logbook)), reverse=True)
    return entries


def _is_readable_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def collect_vessel_records(entries: list[LogbookEntry]) -> list[VesselRecord]:
    return [
        record
        for entry in entries
        if entry.attempt_scorecard is not None
        for record in _entry_records(entry)
    ]


def _load_entry(snapshot: LogbookSnapshot) -> LogbookEntry:
    errors = [snapshot.error] if snapshot.error is not None else []
    benchmark_scorecard_path = _artifact_path(snapshot, "benchmark_scorecard")
    benchmark_scorecard = _load_scorecard(
        benchmark_scorecard_path,
        validate_benchmark_scorecard_document,
        errors,
    )
    attempt_scorecard = _load_scorecard(
        _artifact_path(snapshot, "task_attempt_scorecard"),
        validate_task_attempt_scorecard_document,
        errors,
    )
    if attempt_scorecard is not None:
        attempt_scorecard = normalize_task_attempt_scorecard(attempt_scorecard)
    readiness = _load_scorecard(
        _artifact_path(snapshot, "smoke_readiness_report"),
        validate_smoke_readiness_report_document,
        errors,
    )
    source = benchmark_scorecard or attempt_scorecard or {}
    missing_artifacts = tuple(
        f"{artifact.name}: {artifact.path}"
        for artifact in snapshot.artifacts
        if not artifact.present
    )
    return LogbookEntry(
        logbook=snapshot.logbook,
        updated_at=snapshot.updated_at or _index_timestamp(snapshot.logbook),
        regatta=snapshot.regatta or _optional_source(source, "regatta"),
        course=snapshot.course or _optional_source(source, "course"),
        status=(
            snapshot.status
            if snapshot.state is not LogbookState.LEGACY_SCORECARD_ONLY
            else None
        ),
        outcome=(
            str(readiness["status"])
            if snapshot.run_kind == "real-smoke" and readiness is not None
            else str(benchmark_scorecard["status"])
            if benchmark_scorecard is not None
            else str(attempt_scorecard["status"])
            if attempt_scorecard is not None
            else None
        ),
        benchmark_scorecard=benchmark_scorecard,
        benchmark_scorecard_path=benchmark_scorecard_path,
        attempt_scorecard=attempt_scorecard,
        missing_artifacts=missing_artifacts,
        errors=tuple(errors),
    )


def _artifact_path(snapshot: LogbookSnapshot, name: str) -> Path | None:
    artifact = snapshot.artifact(name)
    return artifact.path if artifact is not None and artifact.file_present else None


def _optional_source(source: dict[str, Any], name: str) -> str | None:
    value = source.get(name)
    return str(value) if value is not None else None


def _index_timestamp(logbook: Path) -> str:
    index_path = logbook / RUN_INDEX_PATH
    source = index_path if index_path.exists() or index_path.is_symlink() else logbook
    return datetime.fromtimestamp(source.lstat().st_mtime).isoformat(timespec="seconds")


def _load_scorecard(
    path: Path | None,
    validator: Any,
    errors: list[str],
) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        errors.append(f"{path.name}: not valid JSON: {error}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{path.name}: must be a JSON object")
        return None
    try:
        validator(payload)
    except SchemaValidationError as error:
        errors.append(f"{path.name}: invalid: {error}")
        return None
    return payload


def _entry_records(entry: LogbookEntry) -> list[VesselRecord]:
    assert entry.attempt_scorecard is not None
    outcomes = _benchmark_outcomes(entry.benchmark_scorecard)
    records = []
    for comparison in entry.attempt_scorecard["comparisons"]:
        comparison_name = str(comparison["name"])
        for vessel in comparison["vessels"]:
            vessel_name = str(vessel["name"])
            provenance = vessel.get("provenance")
            records.append(
                VesselRecord(
                    logbook=str(entry.logbook),
                    regatta=str(entry.attempt_scorecard["regatta"]),
                    course=str(entry.attempt_scorecard["course"]),
                    comparison=comparison_name,
                    vessel=vessel_name,
                    status=str(vessel["status"]),
                    provenance=provenance if isinstance(provenance, dict) else None,
                    usage={
                        "task_attempts": int(vessel["task_attempts"]),
                        "distinct_tool_uses": int(vessel["distinct_tool_uses"]),
                        "total_tokens": int(vessel["total_tokens"]),
                        "total_cost": (
                            float(vessel["total_cost"])
                            if vessel.get("total_cost") is not None
                            else None
                        ),
                        "total_duration_seconds": float(
                            vessel["total_duration_seconds"]
                        ),
                    },
                    outcome=outcomes.get((comparison_name, vessel_name), {}),
                )
            )
    return records


def _benchmark_outcomes(
    scorecard: dict[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if scorecard is None:
        return {}
    outcomes = {}
    for comparison in scorecard["comparisons"]:
        for vessel in comparison["vessels"]:
            outcomes[(str(comparison["name"]), str(vessel["name"]))] = {
                "status": str(vessel["status"]),
                "submitted_instances": int(vessel["submitted_instances"]),
                "resolved_instances": int(vessel["resolved_instances"]),
            }
    return outcomes
