from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.courses.grading import write_course_grading_report


LIVECODEBENCH_GRADING_SCHEMA = "yacht.livecodebench-grading.v1"


def write_livecodebench_grading_report(
    *,
    config_path: Path,
    native_report_path: Path,
    logbook_dir: Path,
    vessel_name: str,
) -> dict[str, Any]:
    return write_course_grading_report(
        config_path=config_path,
        native_report_path=native_report_path,
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
        grading_schema=LIVECODEBENCH_GRADING_SCHEMA,
        native_schema_version=1,
        candidate_label="candidate solutions",
        candidate_record_label="candidate solution",
    )
