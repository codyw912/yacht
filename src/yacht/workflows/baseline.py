"""Recorded-baseline loading and comparability verification (ADR 0018).

A comparison that references a recorded baseline is only honest when
everything that could explain a delta — other than the treatment — held
still between the baseline run and now. These checks turn the provenance
the baseline logbook already records into that guarantee: the adapter
block, task set, and the baseline vessel's configured model and harness
version must match the current config, or the run refuses with every
drifted field named.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yacht.courses.artifacts import grading_report_path, handoff_task_ids
from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.courses.registry import course_adapter_block
from yacht.domain.model import (
    BaselineReference,
    Comparison,
    ConfigError,
    Regatta,
    Vessel,
)
from yacht.logbook.index import RUN_INDEX_PATH
from yacht.logbook.io import load_json_object
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


@dataclass(frozen=True)
class BaselineRecord:
    reference: BaselineReference
    handoff: dict[str, Any]
    grading_report_path: Path
    vessel_scorecard: dict[str, Any] | None
    run_date: str | None


def load_baseline_record(baseline: BaselineReference) -> BaselineRecord:
    handoff_path = baseline.logbook / COURSE_HANDOFF_PATH
    if not handoff_path.exists():
        raise ConfigError(
            f"recorded baseline logbook has no course handoff artifact: {handoff_path}"
        )
    handoff = load_json_object(handoff_path, "recorded baseline course handoff")
    return BaselineRecord(
        reference=baseline,
        handoff=handoff,
        grading_report_path=_baseline_grading_report_path(baseline, handoff),
        vessel_scorecard=_baseline_vessel_scorecard(baseline),
        run_date=_baseline_run_date(baseline),
    )


def verify_baseline_comparability(
    *,
    regatta: Regatta,
    comparison: Comparison,
    current_handoff: dict[str, Any],
    record: BaselineRecord,
) -> None:
    """Refuse the run unless the recorded baseline matches the current config.

    Silently comparing across changed inputs is the failure mode this
    project exists to prevent, so every differing field is named in the
    refusal rather than reported one at a time.
    """
    baseline = record.reference
    mismatches = _adapter_mismatches(current_handoff, record.handoff)
    mismatches.extend(_task_mismatches(current_handoff, record.handoff))
    mismatches.extend(_vessel_mismatches(regatta, baseline, record))
    if not record.grading_report_path.exists():
        mismatches.append(
            "grading report for the baseline vessel was not found: "
            f"{record.grading_report_path}"
        )
    if mismatches:
        raise ConfigError(
            f"comparison {comparison.name} cannot use recorded baseline "
            f"{baseline.logbook} vessel {baseline.vessel}: " + "; ".join(mismatches)
        )


def _baseline_grading_report_path(
    baseline: BaselineReference,
    handoff: dict[str, Any],
) -> Path:
    vessel_path = grading_report_path(
        logbook_dir=baseline.logbook,
        handoff=handoff,
        vessel_name=baseline.vessel,
    )
    if vessel_path.exists():
        return vessel_path
    return grading_report_path(
        logbook_dir=baseline.logbook,
        handoff=handoff,
        vessel_name=None,
    )


def _baseline_vessel_scorecard(
    baseline: BaselineReference,
) -> dict[str, Any] | None:
    scorecard_path = baseline.logbook / TASK_ATTEMPT_SCORECARD_PATH
    if not scorecard_path.exists():
        return None
    scorecard = load_json_object(
        scorecard_path,
        "recorded baseline task attempt scorecard",
    )
    for comparison in scorecard.get("comparisons", ()):
        for vessel in comparison.get("vessels", ()):
            if str(vessel.get("name")) == baseline.vessel:
                return vessel
    return None


def _baseline_run_date(baseline: BaselineReference) -> str | None:
    index_path = baseline.logbook / RUN_INDEX_PATH
    if not index_path.exists():
        return None
    index = load_json_object(index_path, "recorded baseline run index")
    updated_at = index.get("updated_at")
    if isinstance(updated_at, str) and updated_at:
        return updated_at
    return None


def _adapter_mismatches(
    current_handoff: dict[str, Any],
    recorded_handoff: dict[str, Any],
) -> list[str]:
    current = course_adapter_block(current_handoff["adapter"])
    recorded = course_adapter_block(recorded_handoff["adapter"])
    return [
        f"adapter.{key}: recorded {recorded.get(key, 'absent')!r}, "
        f"config {current.get(key, 'absent')!r}"
        for key in sorted(set(current) | set(recorded))
        if current.get(key) != recorded.get(key)
    ]


def _task_mismatches(
    current_handoff: dict[str, Any],
    recorded_handoff: dict[str, Any],
) -> list[str]:
    current_ids = handoff_task_ids(current_handoff)
    recorded_ids = handoff_task_ids(recorded_handoff)
    if current_ids == recorded_ids:
        return []
    deltas = [
        delta
        for label, ids in (
            ("only in config", current_ids - recorded_ids),
            ("only recorded", recorded_ids - current_ids),
        )
        if (delta := _task_id_delta(label, ids))
    ]
    return ["tasks: " + "; ".join(deltas)]


def _task_id_delta(label: str, ids: set[str]) -> str:
    if not ids:
        return ""
    shown = sorted(ids)
    listed = ", ".join(shown[:5])
    if len(shown) > 5:
        listed += f", … ({len(shown)} total)"
    return f"{label}: {listed}"


def _vessel_mismatches(
    regatta: Regatta,
    baseline: BaselineReference,
    record: BaselineRecord,
) -> list[str]:
    vessel = _vessel_by_name(regatta, baseline.vessel)
    mismatches = []
    recorded_model = _recorded_provenance_leaf(record, "model", "configured")
    if recorded_model is None:
        mismatches.append(
            "model.configured: recorded value unavailable (the baseline "
            "logbook records no task-attempt provenance for vessel "
            f"{baseline.vessel}), config {vessel.model!r}"
        )
    elif recorded_model != vessel.model:
        mismatches.append(
            f"model.configured: recorded {recorded_model!r}, config {vessel.model!r}"
        )
    declared_version = _declared_harness_version(regatta, vessel)
    recorded_version = _recorded_provenance_leaf(record, "harness", "version")
    if (
        declared_version is not None
        and recorded_version is not None
        and declared_version != recorded_version
    ):
        mismatches.append(
            f"harness.version: recorded {recorded_version!r}, "
            f"config {declared_version!r}"
        )
    return mismatches


def _declared_harness_version(regatta: Regatta, vessel: Vessel) -> str | None:
    if vessel.runtime is None:
        return None
    runtime = regatta.runtime_recipes.get(vessel.runtime)
    if runtime is None:
        return None
    return runtime.harness_version


def _recorded_provenance_leaf(
    record: BaselineRecord,
    section: str,
    leaf: str,
) -> str | None:
    if record.vessel_scorecard is None:
        return None
    provenance = record.vessel_scorecard.get("provenance")
    if not isinstance(provenance, dict):
        return None
    section_value = provenance.get(section)
    if not isinstance(section_value, dict):
        return None
    value = section_value.get(leaf)
    if isinstance(value, str) and value:
        return value
    return None


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison baseline references undefined vessel {name}")


def comparisons_with_baselines(
    comparisons: tuple[Comparison, ...],
) -> tuple[Comparison, ...]:
    return tuple(
        comparison for comparison in comparisons if comparison.baseline is not None
    )
