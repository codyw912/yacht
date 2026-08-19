from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from yacht.domain.model import Regatta, load_regatta
from yacht.logbook.index import RunIndexLifecycle, start_run_index
from yacht.preflight.runner import AgentPromptRunnerFactory, run_preflight
from yacht.reports.smoke_report import SMOKE_REPORT_PATH, write_smoke_report
from yacht.reports.smoke_readiness import (
    SMOKE_READINESS_REPORT_PATH,
    write_smoke_readiness_report,
)
from yacht.workflows.task_attempt_runner import TaskAgent
from yacht.workflows.task_attempt_runner import run_task_attempts
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH
from yacht.reports.task_attempt_scorecard import write_task_attempt_scorecard


def run_real_smoke_eval(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: Mapping[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory,
    task_agent: TaskAgent,
    agent_name: str,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    index_lifecycle = start_run_index(
        logbook_dir=logbook_dir,
        config_path=config_path,
        run_kind="real-smoke",
        regatta=regatta.name,
        course=regatta.course.name,
        comparisons=regatta.comparisons,
        artifacts=_run_index_artifacts(),
    )
    try:
        return _run_real_smoke_eval(
            config_path=config_path,
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent_prompt_runner_factory=agent_prompt_runner_factory,
            task_agent=task_agent,
            agent_name=agent_name,
            regatta=regatta,
            index_lifecycle=index_lifecycle,
        )
    except BaseException as error:
        index_lifecycle.record_failure(error)
        raise


def _run_real_smoke_eval(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: Mapping[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory,
    task_agent: TaskAgent,
    agent_name: str,
    regatta: Regatta,
    index_lifecycle: RunIndexLifecycle,
) -> dict[str, Any]:
    index_lifecycle.advance("preflight")
    preflight = run_preflight(
        config_path,
        logbook_dir,
        workspace_path,
        secret_values,
        agent_prompt_runner_factory=agent_prompt_runner_factory,
    )
    if preflight["status"] != "passed":
        return _write_summary(
            index_lifecycle=index_lifecycle,
            summary={
                "status": "blocked",
                "regatta": preflight["regatta"],
                "course": preflight["course"],
                "agent": agent_name,
                "preflight": preflight,
                "skipped": ["task-attempts", "smoke-readiness-report", "smoke-report"],
                "artifacts": _artifacts(logbook_dir),
            },
        )

    index_lifecycle.advance("task-attempts")
    attempts = run_task_attempts(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        secret_values=secret_values,
        agent_name=agent_name,
        task_agent=task_agent,
    )
    index_lifecycle.advance("scorecard")
    scorecard = write_task_attempt_scorecard(logbook_dir)
    smoke_eval = {
        "status": scorecard["status"],
        "regatta": scorecard["regatta"],
        "course": scorecard["course"],
        "agent": agent_name,
        "attempts": attempts,
        "scorecard": scorecard,
        "scorecard_path": str(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH),
    }
    readiness = write_smoke_readiness_report(logbook_dir)
    write_smoke_report(logbook_dir)
    return _write_summary(
        index_lifecycle=index_lifecycle,
        summary={
            "status": readiness["status"],
            "regatta": readiness["regatta"],
            "course": readiness["course"],
            "agent": agent_name,
            "preflight": preflight,
            "smoke_eval": smoke_eval,
            "readiness": readiness,
            "readiness_path": str(logbook_dir / SMOKE_READINESS_REPORT_PATH),
            "report_path": str(logbook_dir / SMOKE_REPORT_PATH),
            "artifacts": _artifacts(logbook_dir),
        },
    )


def _artifacts(logbook_dir: Path) -> dict[str, str]:
    return {
        "logbook": str(logbook_dir),
        "smoke_report": str(logbook_dir / SMOKE_REPORT_PATH),
        "smoke_readiness_report": str(logbook_dir / SMOKE_READINESS_REPORT_PATH),
        "task_attempt_scorecard": str(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH),
    }


def _write_summary(
    *,
    summary: dict[str, Any],
    index_lifecycle: RunIndexLifecycle,
) -> dict[str, Any]:
    status = "blocked" if summary["status"] == "blocked" else "complete"
    index_lifecycle.finish(
        status,
        stage="complete" if status == "complete" else None,
    )
    return summary


def _run_index_artifacts() -> dict[str, Path]:
    return {
        "preflight": Path("preflight"),
        "task_attempts": Path("task-attempts"),
        "task_attempt_scorecard": TASK_ATTEMPT_SCORECARD_PATH,
        "smoke_readiness_report": SMOKE_READINESS_REPORT_PATH,
        "smoke_report": SMOKE_REPORT_PATH,
    }
