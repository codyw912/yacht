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
        for field in ("instance_id", "model_name_or_path", "completed"):
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
        if not isinstance(record["completed"], bool):
            raise SystemExit(
                f"candidate records line {line_number}.completed must be a boolean"
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
        str(record["instance_id"]) for record in records if record["completed"] is True
    ]
    unresolved_ids = [
        str(record["instance_id"]) for record in records if record["completed"] is False
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


if __name__ == "__main__":
    raise SystemExit(main())
