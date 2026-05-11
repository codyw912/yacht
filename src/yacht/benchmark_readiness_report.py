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
        "comparison | vessel | status | candidate | runtime | preflight | grading",
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
        "| Comparison | Vessel | Status | Candidate | Runtime | Preflight | Grading |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {_vessel_row(comparison, vessel)} |"
        for comparison, vessel in _vessels(plan)
    )
    return "\n".join(lines) + "\n"


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
        f"{_grading_status(vessel)}"
    )


def _presence(present: bool) -> str:
    return "present" if present else "missing"


def _grading_status(vessel: dict[str, Any]) -> str:
    return "graded" if vessel["grading_report_present"] else "missing"
