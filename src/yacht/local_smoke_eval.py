from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.task_attempt_runner import run_task_attempts
from yacht.task_attempt_scorecard import (
    TASK_ATTEMPT_SCORECARD_PATH,
    write_task_attempt_scorecard,
)


def run_local_smoke_eval(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
) -> dict[str, Any]:
    attempts = run_task_attempts(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        secret_values=secret_values,
        agent_name="local-smoke",
    )
    scorecard = write_task_attempt_scorecard(logbook_dir)
    return {
        "status": scorecard["status"],
        "regatta": scorecard["regatta"],
        "course": scorecard["course"],
        "agent": "local-smoke",
        "attempts": attempts,
        "scorecard": scorecard,
        "scorecard_path": str(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH),
    }
