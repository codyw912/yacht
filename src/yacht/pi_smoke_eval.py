from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.task_attempt_runner import TaskAgent, run_task_attempts
from yacht.task_attempt_scorecard import (
    TASK_ATTEMPT_SCORECARD_PATH,
    write_task_attempt_scorecard,
)


def run_pi_smoke_eval(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    task_agent: TaskAgent,
) -> dict[str, Any]:
    attempts = run_task_attempts(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        secret_values=secret_values,
        agent_name="pi",
        task_agent=task_agent,
    )
    scorecard = write_task_attempt_scorecard(logbook_dir)
    return {
        "status": scorecard["status"],
        "regatta": scorecard["regatta"],
        "course": scorecard["course"],
        "agent": "pi",
        "attempts": attempts,
        "scorecard": scorecard,
        "scorecard_path": str(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH),
    }
