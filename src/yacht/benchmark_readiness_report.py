from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.regatta import ConfigError
from yacht.schemas import SchemaValidationError
from yacht.schemas import validate_benchmark_execution_plan_document


def render_benchmark_readiness_report(
    logbook_dir: Path,
    output_format: str = "text",
) -> str:
    plan_path = logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH
    if not plan_path.exists():
        raise ConfigError(
            f"benchmark execution plan artifact not found: {plan_path}"
        )
    plan = _load_plan(plan_path)
    try:
        validate_benchmark_execution_plan_document(plan)
    except SchemaValidationError as error:
        raise ConfigError(
            f"benchmark execution plan artifact is invalid: {error}"
        ) from error
    if output_format == "summary-json":
        return json.dumps(_summary_json(plan), indent=2, sort_keys=True) + "\n"
    if output_format == "json":
        return json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if output_format == "markdown":
        return _render_markdown(plan)
    return _render_text(plan)


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"benchmark execution plan artifact is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ConfigError("benchmark execution plan artifact must be a JSON object")
    return payload


def _render_text(plan: dict[str, Any]) -> str:
    lines = [
        f"Benchmark readiness: {plan['regatta']} / {plan['course']}",
        f"Status: {plan['status']}",
        "",
        "comparison | vessel | status | candidate | runtime | preflight | grading | details",
    ]
    lines.extend(
        _vessel_row(comparison, vessel) for comparison, vessel in _vessels(plan)
    )
    return "\n".join(lines) + "\n"


def _render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "## Benchmark readiness",
        "",
        f"- Regatta: {plan['regatta']}",
        f"- Course: {plan['course']}",
        f"- Status: {plan['status']}",
        "",
        "| Comparison | Vessel | Status | Candidate | Runtime | Preflight | Grading | Details |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {_vessel_row(comparison, vessel)} |"
        for comparison, vessel in _vessels(plan)
    )
    return "\n".join(lines) + "\n"


def _summary_json(plan: dict[str, Any]) -> dict[str, Any]:
    vessels = _vessels(plan)
    blocked_vessels = [
        _blocked_vessel_summary(comparison, vessel)
        for comparison, vessel in vessels
        if _is_blocked(vessel)
    ]
    return {
        "schema": "yacht.benchmark-readiness-summary.v1",
        "regatta": plan["regatta"],
        "course": plan["course"],
        "status": plan["status"],
        "total_vessels": len(vessels),
        "launchable_vessels": sum(
            1 for _, vessel in vessels if vessel["status"] == "ready-for-grading"
        ),
        "graded_vessels": sum(
            1 for _, vessel in vessels if vessel["status"] == "graded"
        ),
        "blocked_vessel_count": len(blocked_vessels),
        "blocked_vessels": blocked_vessels,
    }


def _blocked_vessel_summary(
    comparison: dict[str, Any],
    vessel: dict[str, Any],
) -> dict[str, Any]:
    return {
        "comparison": comparison["name"],
        "vessel": vessel["name"],
        "status": vessel["status"],
        "details": _artifact_details(vessel),
        "artifact_paths": {
            "candidate_patches": vessel["candidate_patches_path"],
            "preflight": vessel["preflight_artifact_path"],
            "runtime_instances": vessel["runtime_instances_artifact_path"],
            "grading_report": vessel["grading_report_path"],
        },
    }


def _is_blocked(vessel: dict[str, Any]) -> bool:
    return vessel["status"] not in {"ready-for-grading", "graded"}


def _vessels(plan: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (comparison, vessel)
        for comparison in plan["comparisons"]
        for vessel in comparison["vessels"]
    ]


def _vessel_row(comparison: dict[str, Any], vessel: dict[str, Any]) -> str:
    return (
        f"{comparison['name']} | "
        f"{vessel['name']} | "
        f"{vessel['status']} | "
        f"{_presence(vessel['candidate_patches_present'])} | "
        f"{vessel['runtime_snapshot_status']} | "
        f"{vessel['preflight_status']} | "
        f"{_grading_status(vessel)} | "
        f"{_artifact_details(vessel)}"
    )


def _presence(present: bool) -> str:
    return "present" if present else "missing"


def _grading_status(vessel: dict[str, Any]) -> str:
    return "graded" if vessel["grading_report_present"] else "missing"


def _artifact_details(vessel: dict[str, Any]) -> str:
    details: list[str] = []
    if not vessel["candidate_patches_present"]:
        details.append(f"candidate patches: {vessel['candidate_patches_path']}")
    if vessel["runtime_snapshot_status"] != "matched":
        details.append(
            f"runtime instances: {vessel['runtime_instances_artifact_path']}"
        )
    if vessel["preflight_status"] != "passed":
        details.append(f"preflight: {vessel['preflight_artifact_path']}")
    if not vessel["grading_report_present"]:
        details.append(f"grading report: {vessel['grading_report_path']}")
    return "; ".join(details) if details else "-"
