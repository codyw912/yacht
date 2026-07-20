from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.config.loader import load_regatta
from yacht.courses.artifacts import (
    candidate_patches_path,
    validate_handoff_vessel,
    vessel_artifact_dir,
    write_json_artifact,
    write_jsonl_records,
)
from yacht.courses.handoff import COURSE_HANDOFF_PATH, build_course_handoff
from yacht.courses.terminal_bench.job import (
    TERMINAL_BENCH_JOB_FILENAME,
    render_terminal_bench_job,
)


def write_terminal_bench_rollout_plan(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    handoff = build_course_handoff(config_path)
    validate_handoff_vessel(handoff, vessel_name)
    regatta = load_regatta(config_path)
    job = render_terminal_bench_job(regatta=regatta, vessel_name=vessel_name)
    records = [
        {
            "instance_id": str(task["id"]),
            "model_name_or_path": vessel_name,
        }
        for task in handoff["tasks"]
    ]

    write_json_artifact(logbook_dir / COURSE_HANDOFF_PATH, handoff)
    roster_path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    write_jsonl_records(roster_path, records)
    job_path = (
        vessel_artifact_dir(
            logbook_dir=logbook_dir,
            handoff=handoff,
            vessel_name=vessel_name,
        )
        / TERMINAL_BENCH_JOB_FILENAME
    )
    write_json_artifact(job_path, job)

    return {
        "status": "validated",
        "adapter": str(handoff["adapter"]["kind"]),
        "dataset": str(handoff["adapter"]["dataset"]),
        "split": str(handoff["adapter"]["split"]),
        "prediction_count": len(records),
        "instance_ids": [record["instance_id"] for record in records],
        "candidate_patches_path": str(roster_path),
        "terminal_bench_job_path": str(job_path),
        "vessel": vessel_name,
    }
