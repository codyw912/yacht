from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run YACHT custom eval grading.")
    parser.add_argument("--candidate-records", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    candidate_path = Path(args.candidate_records)
    records = _load_candidate_records(candidate_path)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    vessel_name = str(records[0]["model_name_or_path"])
    report_path = report_dir / f"{vessel_name}.{args.run_id}.json"
    report_path.write_text(
        json.dumps(_native_report(records), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(str(report_path))
    return 0


def _load_candidate_records(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"candidate records line {line_number} is not valid JSON: {error}"
            ) from error
        if not isinstance(record, dict):
            raise SystemExit(f"candidate records line {line_number} must be an object")
        for field in (
            "instance_id",
            "model_name_or_path",
            "expect_response",
            "tool_calls",
            "expect_tool_calls",
        ):
            if field not in record:
                raise SystemExit(f"candidate records line {line_number}.{field} missing")
        if not isinstance(record["instance_id"], str) or not record["instance_id"]:
            raise SystemExit(
                f"candidate records line {line_number}.instance_id must be non-empty"
            )
        if (
            not isinstance(record["model_name_or_path"], str)
            or not record["model_name_or_path"]
        ):
            raise SystemExit(
                "candidate records line "
                f"{line_number}.model_name_or_path must be non-empty"
            )
        if not isinstance(record["expect_response"], dict) or not record[
            "expect_response"
        ]:
            raise SystemExit(
                "candidate records line "
                f"{line_number}.expect_response must be a non-empty object"
            )
        for key, expected in record["expect_response"].items():
            if not isinstance(key, str) or not key:
                raise SystemExit(
                    "candidate records line "
                    f"{line_number}.expect_response keys must be non-empty strings"
                )
            if not isinstance(expected, str | bool | int | float):
                raise SystemExit(
                    "candidate records line "
                    f"{line_number}.expect_response.{key} must be a scalar"
                )
        response = record.get("response")
        if response is not None and not isinstance(response, dict):
            raise SystemExit(
                f"candidate records line {line_number}.response must be an object or null"
            )
        for field in ("tool_calls", "expect_tool_calls"):
            if not isinstance(record[field], list) or not all(
                isinstance(tool_call, str) and tool_call for tool_call in record[field]
            ):
                raise SystemExit(
                    f"candidate records line {line_number}.{field} must be a list "
                    "of non-empty strings"
                )
        records.append(record)
    if not records:
        raise SystemExit("candidate records must contain at least one record")
    vessel_names = {str(record["model_name_or_path"]) for record in records}
    if len(vessel_names) != 1:
        raise SystemExit("candidate records must contain exactly one vessel")
    return records


def _native_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    submitted_ids = [str(record["instance_id"]) for record in records]
    resolved_ids = [
        str(record["instance_id"]) for record in records if _record_resolved(record)
    ]
    unresolved_ids = [
        str(record["instance_id"]) for record in records if not _record_resolved(record)
    ]
    return {
        "schema_version": 1,
        "total_instances": len(records),
        "submitted_instances": len(records),
        "completed_instances": len(records),
        "resolved_instances": len(resolved_ids),
        "unresolved_instances": len(unresolved_ids),
        "submitted_ids": submitted_ids,
        "completed_ids": submitted_ids,
        "incomplete_ids": [],
        "resolved_ids": resolved_ids,
        "unresolved_ids": unresolved_ids,
        "empty_patch_instances": 0,
        "empty_patch_ids": [],
        "error_instances": 0,
        "error_ids": [],
    }


def _record_resolved(record: dict[str, Any]) -> bool:
    response = record.get("response")
    if not isinstance(response, dict):
        return False
    expectations = record["expect_response"]
    assert isinstance(expectations, dict)
    expected_tools = set(record["expect_tool_calls"])
    actual_tools = set(record["tool_calls"])
    return (
        all(response.get(key) == expected for key, expected in expectations.items())
        and expected_tools <= actual_tools
    )


if __name__ == "__main__":
    raise SystemExit(main())
