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
)
from yacht.domain.model import ConfigError
from yacht.logbook.index import RUN_INDEX_PATH
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


_LOGBOOK_MARKERS = (
    BENCHMARK_SCORECARD_PATH,
    TASK_ATTEMPT_SCORECARD_PATH,
    RUN_INDEX_PATH,
)


@dataclass(frozen=True)
class LogbookEntry:
    logbook: Path
    updated_at: str
    regatta: str | None = None
    course: str | None = None
    benchmark_scorecard: dict[str, Any] | None = None
    attempt_scorecard: dict[str, Any] | None = None
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
        if any(_is_marker_file(candidate / marker) for marker in _LOGBOOK_MARKERS):
            entries.append(_load_entry(candidate))
    entries.sort(key=lambda entry: (entry.updated_at, str(entry.logbook)), reverse=True)
    return entries


def _is_readable_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _is_marker_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def collect_vessel_records(entries: list[LogbookEntry]) -> list[VesselRecord]:
    return [
        record
        for entry in entries
        if entry.attempt_scorecard is not None
        for record in _entry_records(entry)
    ]


def _load_entry(logbook: Path) -> LogbookEntry:
    errors: list[str] = []
    benchmark_scorecard = _load_scorecard(
        logbook / BENCHMARK_SCORECARD_PATH,
        validate_benchmark_scorecard_document,
        errors,
    )
    attempt_scorecard = _load_scorecard(
        logbook / TASK_ATTEMPT_SCORECARD_PATH,
        validate_task_attempt_scorecard_document,
        errors,
    )
    source = benchmark_scorecard or attempt_scorecard or {}
    marker_paths = [
        logbook / marker for marker in _LOGBOOK_MARKERS if (logbook / marker).is_file()
    ]
    updated_timestamp = max(path.stat().st_mtime for path in marker_paths)
    return LogbookEntry(
        logbook=logbook,
        updated_at=datetime.fromtimestamp(updated_timestamp).isoformat(
            timespec="seconds"
        ),
        regatta=str(source["regatta"]) if "regatta" in source else None,
        course=str(source["course"]) if "course" in source else None,
        benchmark_scorecard=benchmark_scorecard,
        attempt_scorecard=attempt_scorecard,
        errors=tuple(errors),
    )


def _load_scorecard(
    path: Path,
    validator: Any,
    errors: list[str],
) -> dict[str, Any] | None:
    if not path.is_file():
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
                        "tool_call_count": int(vessel["tool_call_count"]),
                        "total_tokens": int(vessel["total_tokens"]),
                        "total_cost": float(vessel.get("total_cost", 0.0)),
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
