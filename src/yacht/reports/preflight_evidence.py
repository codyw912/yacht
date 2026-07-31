from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.courses.handoff import load_course_handoff
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
    SchemaValidationError,
    validate_preflight_document,
    validate_preflight_evidence_report_document,
)


PREFLIGHT_EVIDENCE_REPORT_PATH = Path("preflight-evidence-report.json")


def write_preflight_evidence_report(logbook_dir: Path) -> dict[str, Any]:
    report = build_preflight_evidence_report(logbook_dir)
    _write_json(logbook_dir / PREFLIGHT_EVIDENCE_REPORT_PATH, report)
    return report


def render_preflight_evidence_report(
    report: dict[str, Any],
    output_format: str = "json",
) -> str:
    if output_format == "json":
        return json.dumps(report, indent=2) + "\n"
    if output_format == "markdown":
        return _render_markdown(report)
    if output_format == "text":
        return _render_text(report)
    raise ValueError(f"unsupported preflight report output format: {output_format}")


def build_preflight_evidence_report(logbook_dir: Path) -> dict[str, Any]:
    handoff = load_course_handoff(logbook_dir)
    report = _build_report(logbook_dir, handoff)
    validate_preflight_evidence_report_document(report)
    return report


def _build_report(logbook_dir: Path, handoff: dict[str, Any]) -> dict[str, Any]:
    comparisons = [
        _comparison_to_json(
            logbook_dir=logbook_dir,
            handoff=handoff,
            comparison=comparison,
        )
        for comparison in handoff["comparisons"]
    ]
    return {
        "schema": PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
        "regatta": str(handoff["regatta"]),
        "course": str(handoff["course"]),
        "status": _aggregate_status(
            [comparison["status"] for comparison in comparisons]
        ),
        "comparisons": comparisons,
    }


def _comparison_to_json(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    vessels = [
        _vessel_to_json(
            logbook_dir=logbook_dir,
            regatta_name=str(handoff["regatta"]),
            comparison_name=str(comparison["name"]),
            vessel_name=str(vessel_name),
        )
        for vessel_name in comparison["vessels"]
    ]
    return {
        "name": str(comparison["name"]),
        "course": str(comparison["course"]),
        "status": _aggregate_status([vessel["status"] for vessel in vessels]),
        "vessels": vessels,
    }


def _vessel_to_json(
    *,
    logbook_dir: Path,
    regatta_name: str,
    comparison_name: str,
    vessel_name: str,
) -> dict[str, Any]:
    artifact_path = logbook_dir / "preflight" / comparison_name / f"{vessel_name}.json"
    if not artifact_path.exists():
        return _vessel_report(
            vessel_name=vessel_name,
            artifact_path=artifact_path,
            artifact_present=False,
            status="missing-preflight",
            preflight_status="missing",
            reason="preflight-missing",
            error=None,
        )

    try:
        artifact = _load_preflight_artifact(artifact_path)
        _validate_artifact_identity(
            artifact=artifact,
            regatta_name=regatta_name,
            comparison_name=comparison_name,
            vessel_name=vessel_name,
        )
    except ConfigError as error:
        return _vessel_report(
            vessel_name=vessel_name,
            artifact_path=artifact_path,
            artifact_present=True,
            status="preflight-invalid",
            preflight_status="invalid",
            reason="preflight-invalid",
            error=str(error),
        )

    preflight_status = str(artifact["status"])
    if preflight_status == "passed":
        return _vessel_report(
            vessel_name=vessel_name,
            artifact_path=artifact_path,
            artifact_present=True,
            status="eligible",
            preflight_status=preflight_status,
            reason="preflight-passed",
            error=None,
        )
    status = _blocked_status(artifact, preflight_status)
    return _vessel_report(
        vessel_name=vessel_name,
        artifact_path=artifact_path,
        artifact_present=True,
        status=status,
        preflight_status=preflight_status,
        reason=status,
        error=None,
    )


def _blocked_status(artifact: dict[str, Any], preflight_status: str) -> str:
    if preflight_status == "failed" and any(
        str(check.get("kind")) == "runtime-capability"
        and str(check.get("status")) == "failed"
        for check in artifact["checks"]
    ):
        return "unsupported-rigging-capability"
    return f"preflight-{preflight_status}"


def _load_preflight_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"preflight artifact is not valid JSON: {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ConfigError(f"preflight artifact must be a JSON object: {path}")
    try:
        validate_preflight_document(payload)
    except SchemaValidationError as error:
        raise ConfigError(f"preflight artifact is invalid: {path}: {error}") from error
    return payload


def _validate_artifact_identity(
    *,
    artifact: dict[str, Any],
    regatta_name: str,
    comparison_name: str,
    vessel_name: str,
) -> None:
    expected = {
        "regatta": regatta_name,
        "comparison": comparison_name,
        "vessel": vessel_name,
    }
    mismatches = [
        f"{key}={artifact.get(key)!r}, expected {value!r}"
        for key, value in expected.items()
        if artifact.get(key) != value
    ]
    if mismatches:
        raise ConfigError(
            "preflight artifact identity does not match course handoff: "
            f"{', '.join(mismatches)}"
        )


def _vessel_report(
    *,
    vessel_name: str,
    artifact_path: Path,
    artifact_present: bool,
    status: str,
    preflight_status: str,
    reason: str,
    error: str | None,
) -> dict[str, Any]:
    report = {
        "name": vessel_name,
        "status": status,
        "eligible_for_benchmark": status == "eligible",
        "reason": reason,
        "preflight_artifact_path": str(artifact_path),
        "preflight_artifact_present": artifact_present,
        "preflight_status": preflight_status,
    }
    if error is not None:
        report["error"] = error
    return report


def _aggregate_status(statuses: list[str]) -> str:
    if all(status in {"ready", "eligible"} for status in statuses):
        return "ready"
    return "blocked"


def _render_text(report: dict[str, Any]) -> str:
    summary = _report_summary(report)
    lines = [
        f"Preflight report: {report['regatta']} / {report['course']}",
        f"Status: {report['status']}",
        (
            "Summary: "
            f"eligible={summary['eligible']} | "
            f"blocked={summary['blocked']} | "
            f"missing={summary['missing']} | "
            f"invalid={summary['invalid']} | "
            f"total={summary['total']}"
        ),
        "",
        "comparison | vessel | status | eligible | reason | preflight | artifact",
    ]
    lines.extend(_text_vessel_row(row) for row in _vessel_rows(report))
    return "\n".join(lines) + "\n"


def _render_markdown(report: dict[str, Any]) -> str:
    summary = _report_summary(report)
    lines = [
        "## Preflight report",
        "",
        f"- Regatta: {report['regatta']}",
        f"- Course: {report['course']}",
        f"- Status: {report['status']}",
        (
            "- Summary: "
            f"eligible={summary['eligible']}, "
            f"blocked={summary['blocked']}, "
            f"missing={summary['missing']}, "
            f"invalid={summary['invalid']}, "
            f"total={summary['total']}"
        ),
        "",
        "| Comparison | Vessel | Status | Eligible | Reason | Preflight | Artifact |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_markdown_vessel_row(row) for row in _vessel_rows(report))
    return "\n".join(lines) + "\n"


def _report_summary(report: dict[str, Any]) -> dict[str, int]:
    rows = _vessel_rows(report)
    return {
        "total": len(rows),
        "eligible": sum(1 for row in rows if row["eligible"]),
        "blocked": sum(1 for row in rows if not row["eligible"]),
        "missing": sum(1 for row in rows if row["preflight_status"] == "missing"),
        "invalid": sum(1 for row in rows if row["preflight_status"] == "invalid"),
    }


def _vessel_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for comparison in report["comparisons"]:
        for vessel in comparison["vessels"]:
            rows.append(
                {
                    "comparison": str(comparison["name"]),
                    "vessel": str(vessel["name"]),
                    "status": str(vessel["status"]),
                    "eligible": bool(vessel["eligible_for_benchmark"]),
                    "reason": str(vessel["reason"]),
                    "preflight_status": str(vessel["preflight_status"]),
                    "artifact": str(vessel["preflight_artifact_path"]),
                }
            )
    return rows


def _text_vessel_row(row: dict[str, Any]) -> str:
    eligible = "yes" if row["eligible"] else "no"
    return (
        f"{row['comparison']} | {row['vessel']} | {row['status']} | "
        f"{eligible} | {row['reason']} | {row['preflight_status']} | "
        f"{row['artifact']}"
    )


def _markdown_vessel_row(row: dict[str, Any]) -> str:
    eligible = "yes" if row["eligible"] else "no"
    return (
        f"| {row['comparison']} | {row['vessel']} | {row['status']} | "
        f"{eligible} | {row['reason']} | {row['preflight_status']} | "
        f"{row['artifact']} |"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
