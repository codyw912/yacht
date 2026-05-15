from __future__ import annotations

from pathlib import Path
from typing import Any

from yacht.pi_smoke_eval import run_pi_smoke_eval
from yacht.preflight_runner import AgentPromptRunnerFactory, run_preflight
from yacht.smoke_report import SMOKE_REPORT_PATH, write_smoke_report
from yacht.smoke_readiness_report import (
    SMOKE_READINESS_REPORT_PATH,
    write_smoke_readiness_report,
)
from yacht.task_attempt_runner import TaskAgent


def run_real_smoke_eval(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory,
    task_agent: TaskAgent,
) -> dict[str, Any]:
    preflight = run_preflight(
        config_path,
        logbook_dir,
        workspace_path,
        secret_values,
        agent_prompt_runner_factory=agent_prompt_runner_factory,
    )
    if preflight["status"] != "passed":
        return {
            "status": "blocked",
            "regatta": preflight["regatta"],
            "course": preflight["course"],
            "agent": "pi",
            "preflight": preflight,
            "skipped": ["pi-smoke-eval", "smoke-readiness-report", "smoke-report"],
        }

    smoke_eval = run_pi_smoke_eval(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        secret_values=secret_values,
        task_agent=task_agent,
    )
    readiness = write_smoke_readiness_report(logbook_dir)
    write_smoke_report(logbook_dir)
    return {
        "status": readiness["status"],
        "regatta": readiness["regatta"],
        "course": readiness["course"],
        "agent": "pi",
        "preflight": preflight,
        "smoke_eval": smoke_eval,
        "readiness": readiness,
        "readiness_path": str(logbook_dir / SMOKE_READINESS_REPORT_PATH),
        "report_path": str(logbook_dir / SMOKE_REPORT_PATH),
    }
