from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.contracts.schemas import TERMINAL_BENCH_GRADING_SCHEMA
from yacht.courses.grading import write_course_grading_report


def write_terminal_bench_grading_report(
    *,
    config_path: Path,
    native_report_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    grading_schema: str = TERMINAL_BENCH_GRADING_SCHEMA,
) -> dict[str, Any]:
    return write_course_grading_report(
        config_path=config_path,
        native_report_path=native_report_path,
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
        grading_schema=grading_schema,
        native_schema_version=1,
        candidate_label="task roster",
        candidate_record_label="task roster",
    )
