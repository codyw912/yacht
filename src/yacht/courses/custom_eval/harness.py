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
    instance_results = [_instance_result(record) for record in records]
    submitted_ids = [str(record["instance_id"]) for record in records]
    resolved_ids = [
        str(result["instance_id"]) for result in instance_results if result["resolved"]
    ]
    unresolved_ids = [
        str(result["instance_id"])
        for result in instance_results
        if not result["resolved"]
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
        "instance_results": instance_results,
    }


def _instance_result(record: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response")
    missing_response_fields: list[str] = []
    mismatched_response_fields: list[str] = []
    if isinstance(response, dict):
        expectations = record["expect_response"]
        assert isinstance(expectations, dict)
        for key, expected in expectations.items():
            if key not in response:
                missing_response_fields.append(str(key))
            elif response.get(key) != expected:
                mismatched_response_fields.append(str(key))
        response_matched = not missing_response_fields and not mismatched_response_fields
    else:
        response_matched = False

    expected_tool_calls = list(record["expect_tool_calls"])
    observed_tool_calls = list(record["tool_calls"])
    missing_tool_calls = [
        tool_call
        for tool_call in expected_tool_calls
        if tool_call not in observed_tool_calls
    ]
    resolved = response_matched and not missing_tool_calls
    return {
        "instance_id": str(record["instance_id"]),
        "resolved": resolved,
        "response_matched": response_matched,
        "missing_response_fields": missing_response_fields,
        "mismatched_response_fields": mismatched_response_fields,
        "expected_tool_calls": expected_tool_calls,
        "observed_tool_calls": observed_tool_calls,
        "missing_tool_calls": missing_tool_calls,
        "reason": _result_reason(
            resolved=resolved,
            response=response,
            missing_response_fields=missing_response_fields,
            mismatched_response_fields=mismatched_response_fields,
            missing_tool_calls=missing_tool_calls,
        ),
    }


def _result_reason(
    *,
    resolved: bool,
    response: Any,
    missing_response_fields: list[str],
    mismatched_response_fields: list[str],
    missing_tool_calls: list[str],
) -> str:
    if resolved:
        return "resolved"
    if not isinstance(response, dict):
        return "response_not_json_object"
    if missing_response_fields:
        return f"missing_response_fields: {', '.join(missing_response_fields)}"
    if mismatched_response_fields:
        return f"mismatched_response_fields: {', '.join(mismatched_response_fields)}"
    if missing_tool_calls:
        return f"missing_tool_calls: {', '.join(missing_tool_calls)}"
    return "unresolved"


if __name__ == "__main__":
    raise SystemExit(main())
