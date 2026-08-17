from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yacht.reports.benchmark_aggregate import BENCHMARK_AGGREGATE_PATH
from yacht.reports.benchmark_aggregate import build_benchmark_aggregate
from yacht.reports.benchmark_aggregate import render_benchmark_aggregate_document
from yacht.workflows.benchmark_launch import CommandRunner
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.reports.next_steps import command_step
from yacht.preflight.runner import AgentPromptRunnerFactory
from yacht.workflows.real_benchmark_eval import REAL_BENCHMARK_EVAL_PATH
from yacht.workflows.real_benchmark_eval import ProgressReporter
from yacht.workflows.real_benchmark_eval import run_real_benchmark_eval
from yacht.domain.model import ConfigError, load_regatta
from yacht.reports.surface_metadata import regatta_surfaces_to_json
from yacht.workflows.task_attempt_runner import TaskAgent
from yacht.contracts.schemas import (
    REAL_BENCHMARK_REPETITIONS_SCHEMA,
    validate_real_benchmark_repetitions_document,
)


REAL_BENCHMARK_REPETITIONS_PATH = Path("real-benchmark-repetitions.json")
REPETITION_RUNS_DIR = Path("runs")
BENCHMARK_REPORT_MARKDOWN_PATH = Path("benchmark-report.md")

EvalRunner = Callable[[Path], dict[str, Any]]


def run_real_benchmark_repetitions(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    repetitions: int,
    agent_name: str | None = None,
    agent_prompt_runner_factory: AgentPromptRunnerFactory | None = None,
    task_agent: TaskAgent | None = None,
    benchmark_command_runner: CommandRunner | None = None,
    max_workers: int = 1,
    eval_runner: EvalRunner | None = None,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    if repetitions < 1:
        raise ConfigError("real benchmark repetitions must be at least 1")
    regatta = load_regatta(config_path)
    surfaces = regatta_surfaces_to_json(regatta)
    _progress(
        progress,
        f"real benchmark repetitions started: {regatta.name} / {regatta.course.name}; "
        f"repetitions={repetitions}; logbook={logbook_dir}",
    )
    if eval_runner is None:
        if agent_name is None:
            raise ConfigError("real benchmark repetitions require an agent name")
        eval_runner = _real_benchmark_eval_runner(
            config_path=config_path,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent_name=agent_name,
            agent_prompt_runner_factory=agent_prompt_runner_factory,
            task_agent=task_agent,
            benchmark_command_runner=benchmark_command_runner,
            max_workers=max_workers,
            progress=progress,
        )

    runs = []
    aggregate_logbooks = []
    for index in range(1, repetitions + 1):
        child_logbook = logbook_dir / REPETITION_RUNS_DIR / f"run-{index:03d}"
        if child_logbook.exists():
            raise ConfigError(
                f"repetition child logbook already exists: {child_logbook}"
            )
        _progress(
            progress,
            f"repetition {index}/{repetitions} started: logbook={child_logbook}",
        )
        run_summary = eval_runner(child_logbook)
        scorecard_path = child_logbook / BENCHMARK_SCORECARD_PATH
        scorecard_present = scorecard_path.is_file()
        _progress(
            progress,
            f"repetition {index}/{repetitions} finished: "
            f"status={run_summary.get('status', 'unknown')}; "
            f"scorecard={'present' if scorecard_present else 'missing'}",
        )
        if scorecard_present:
            aggregate_logbooks.append(child_logbook)
        runs.append(
            {
                "index": index,
                "logbook": str(child_logbook),
                "status": str(run_summary.get("status", "unknown")),
                "scorecard_present": scorecard_present,
                "artifacts": {
                    "real_benchmark_eval": str(
                        child_logbook / REAL_BENCHMARK_EVAL_PATH
                    ),
                    "benchmark_scorecard": str(scorecard_path),
                },
            }
        )

    aggregate = None
    if aggregate_logbooks:
        _progress(
            progress,
            f"benchmark aggregate: writing {len(aggregate_logbooks)} completed run(s)",
        )
        aggregate = build_benchmark_aggregate(aggregate_logbooks)
        _write_json(logbook_dir / BENCHMARK_AGGREGATE_PATH, aggregate)
        (logbook_dir / BENCHMARK_REPORT_MARKDOWN_PATH).write_text(
            render_benchmark_aggregate_document(aggregate, "markdown"),
            encoding="utf-8",
        )
    else:
        _progress(progress, "benchmark aggregate: skipped; no completed runs")

    summary = _summary(
        regatta=regatta.name,
        course=regatta.course.name,
        agent_name=agent_name,
        surfaces=surfaces,
        logbook_dir=logbook_dir,
        repetitions=repetitions,
        runs=runs,
        aggregate=aggregate,
    )
    validate_real_benchmark_repetitions_document(summary)
    _progress(progress, f"real benchmark repetitions complete: {summary['status']}")
    return _write_json(logbook_dir / REAL_BENCHMARK_REPETITIONS_PATH, summary)


def _real_benchmark_eval_runner(
    *,
    config_path: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_name: str,
    agent_prompt_runner_factory: AgentPromptRunnerFactory,
    task_agent: TaskAgent,
    benchmark_command_runner: CommandRunner | None,
    max_workers: int,
    progress: ProgressReporter | None,
) -> EvalRunner:
    def run(child_logbook: Path) -> dict[str, Any]:
        return run_real_benchmark_eval(
            config_path=config_path,
            logbook_dir=child_logbook,
            workspace_path=workspace_path,
            secret_values=secret_values,
            agent_prompt_runner_factory=agent_prompt_runner_factory,
            task_agent=task_agent,
            agent_name=agent_name,
            benchmark_command_runner=benchmark_command_runner,
            max_workers=max_workers,
            progress=progress,
        )

    return run


def _summary(
    *,
    regatta: str,
    course: str,
    agent_name: str | None,
    surfaces: dict[str, Any],
    logbook_dir: Path,
    repetitions: int,
    runs: list[dict[str, Any]],
    aggregate: dict[str, Any] | None,
) -> dict[str, Any]:
    completed_runs = sum(1 for run in runs if run["scorecard_present"])
    failed_runs = repetitions - completed_runs
    status = "complete"
    if completed_runs == 0:
        status = "blocked"
    elif failed_runs:
        status = "partial"
    summary: dict[str, Any] = {
        "schema": REAL_BENCHMARK_REPETITIONS_SCHEMA,
        "status": status,
        "regatta": regatta,
        "course": course,
        "surfaces": surfaces,
        "summary": {
            "repetitions": repetitions,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "aggregate_logbooks": completed_runs,
        },
        "runs": runs,
        "artifacts": {
            "logbook": str(logbook_dir),
            "real_benchmark_repetitions": str(
                logbook_dir / REAL_BENCHMARK_REPETITIONS_PATH
            ),
            "benchmark_aggregate": str(logbook_dir / BENCHMARK_AGGREGATE_PATH),
            "benchmark_report_markdown": str(
                logbook_dir / BENCHMARK_REPORT_MARKDOWN_PATH
            ),
        },
        "next_steps": _next_steps(logbook_dir, runs),
    }
    if agent_name is not None:
        summary["agent"] = agent_name
    if aggregate is not None:
        summary["aggregate_summary"] = _aggregate_summary(aggregate)
    return summary


def _aggregate_summary(aggregate: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_count": aggregate["run_count"],
        "comparisons": [
            {
                "name": comparison["name"],
                "baseline": comparison["baseline"],
                "challenger": comparison["challenger"],
                "delta": comparison["delta"],
                "vessels": [
                    {
                        "name": vessel["name"],
                        "submitted_instances": vessel["submitted_instances"],
                        "resolved_instances": vessel["resolved_instances"],
                        "resolution_rate": vessel["resolution_rate"],
                        "total_tokens": vessel["total_tokens"],
                        "total_cost": vessel["total_cost"],
                        "total_duration_seconds": vessel["total_duration_seconds"],
                        "total_distinct_tool_uses": vessel["total_distinct_tool_uses"],
                    }
                    for vessel in comparison["vessels"]
                ],
            }
            for comparison in aggregate["comparisons"]
        ],
    }


def _next_steps(
    logbook_dir: Path, runs: list[dict[str, Any]]
) -> list[dict[str, object]]:
    aggregate_logbooks = [
        str(run["logbook"]) for run in runs if bool(run["scorecard_present"])
    ]
    if not aggregate_logbooks:
        return [
            command_step(
                label="Inspect child benchmark runs",
                reason=(
                    "No repetition produced a benchmark scorecard. Inspect the "
                    "child logbooks to find the first blocked stage."
                ),
                command=[
                    "uv",
                    "run",
                    "yacht",
                    "status",
                    "--logbook",
                    str(runs[0]["logbook"]),
                ],
            )
        ]
    return [
        command_step(
            label="Render benchmark report",
            reason=(
                "At least one repetition produced a benchmark scorecard; render the "
                "parent aggregate report with benchmark outcomes and usage."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "report",
                "--logbook",
                str(logbook_dir),
            ],
        )
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _progress(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
