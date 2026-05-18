from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yacht.benchmark_grading_collection import (
    BENCHMARK_GRADING_COLLECTION_PATH,
    collect_benchmark_grading_reports,
)
from yacht.benchmark_execution_plan import (
    BENCHMARK_EXECUTION_PLAN_PATH,
    write_benchmark_execution_plan,
)
from yacht.benchmark_launch import (
    BENCHMARK_LAUNCH_RESULT_PATH,
    CommandRunner,
    write_benchmark_launch_result,
)
from yacht.benchmark_launcher_handoff import (
    BENCHMARK_LAUNCHER_HANDOFF_PATH,
    DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
    write_benchmark_launcher_handoff,
)
from yacht.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.benchmark_scorecard import write_benchmark_scorecard
from yacht.course_handoff import write_course_handoff
from yacht.next_steps import command_step
from yacht.preflight_evidence_report import PREFLIGHT_EVIDENCE_REPORT_PATH
from yacht.preflight_evidence_report import write_preflight_evidence_report
from yacht.preflight_runner import AgentPromptRunnerFactory, run_preflight
from yacht.readiness_gate import evaluate_readiness_gate
from yacht.regatta import ConfigError, load_regatta
from yacht.runtime_instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.runtime_instances import write_runtime_instances_plan
from yacht.swebench_predictions_from_attempts import (
    write_swe_bench_predictions_from_attempts,
)
from yacht.task_attempt_runner import TaskAgent, run_task_attempts
from yacht.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH
from yacht.task_attempt_scorecard import write_task_attempt_scorecard


REAL_BENCHMARK_EVAL_PATH = Path("real-benchmark-eval.json")


def run_real_benchmark_eval(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_values: dict[str, str],
    agent_prompt_runner_factory: AgentPromptRunnerFactory,
    task_agent: TaskAgent,
    benchmark_command_runner: CommandRunner | None = None,
    max_workers: int = 1,
    python_executable: str = DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    course_handoff = write_course_handoff(config_path, logbook_dir)
    preflight = run_preflight(
        config_path,
        logbook_dir,
        workspace_path,
        secret_values,
        agent_prompt_runner_factory=agent_prompt_runner_factory,
    )
    preflight_evidence_report = write_preflight_evidence_report(logbook_dir)
    if preflight["status"] != "passed":
        return _write_summary(
            logbook_dir,
            _blocked_summary(
                regatta=regatta.name,
                course=regatta.course.name,
                course_handoff=course_handoff,
                preflight=preflight,
                preflight_evidence_report=preflight_evidence_report,
                skipped=[
                    "task-attempts",
                    "predictions-from-attempts",
                    "runtime-instances",
                    "benchmark-plan",
                    "benchmark-launcher",
                    "benchmark-launch",
                    "benchmark-collect-grading",
                    "benchmark-scorecard",
                ],
                logbook_dir=logbook_dir,
            ),
        )

    attempts = run_task_attempts(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        secret_values=secret_values,
        agent_name="pi",
        task_agent=task_agent,
    )
    task_scorecard = write_task_attempt_scorecard(logbook_dir)
    if attempts["status"] != "completed":
        return _write_summary(
            logbook_dir,
            _blocked_summary(
                regatta=regatta.name,
                course=regatta.course.name,
                course_handoff=course_handoff,
                preflight=preflight,
                preflight_evidence_report=preflight_evidence_report,
                attempts=attempts,
                task_attempt_scorecard=task_scorecard,
                skipped=[
                    "predictions-from-attempts",
                    "runtime-instances",
                    "benchmark-plan",
                    "benchmark-launcher",
                    "benchmark-launch",
                    "benchmark-collect-grading",
                    "benchmark-scorecard",
                ],
                logbook_dir=logbook_dir,
            ),
        )

    predictions = []
    try:
        for comparison in regatta.comparisons:
            for vessel_name in comparison.vessels:
                predictions.append(
                    write_swe_bench_predictions_from_attempts(
                        config_path=config_path,
                        logbook_dir=logbook_dir,
                        vessel_name=vessel_name,
                        comparison_name=comparison.name,
                    )
                )
    except ConfigError as error:
        return _write_summary(
            logbook_dir,
            _blocked_summary(
                regatta=regatta.name,
                course=regatta.course.name,
                course_handoff=course_handoff,
                preflight=preflight,
                preflight_evidence_report=preflight_evidence_report,
                attempts=attempts,
                task_attempt_scorecard=task_scorecard,
                predictions=predictions,
                failed_stage="predictions-from-attempts",
                error=str(error),
                skipped=[
                    "runtime-instances",
                    "benchmark-plan",
                    "benchmark-launcher",
                    "benchmark-launch",
                    "benchmark-collect-grading",
                    "benchmark-scorecard",
                ],
                logbook_dir=logbook_dir,
                next_steps=_prediction_failure_next_steps(logbook_dir),
            ),
        )
    runtime_instances = write_runtime_instances_plan(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
    )
    benchmark_plan = write_benchmark_execution_plan(logbook_dir)
    readiness_gate = evaluate_readiness_gate(logbook_dir)
    if readiness_gate.blocked_vessel_count:
        return _write_summary(
            logbook_dir,
            _blocked_summary(
                regatta=regatta.name,
                course=regatta.course.name,
                course_handoff=course_handoff,
                preflight=preflight,
                preflight_evidence_report=preflight_evidence_report,
                attempts=attempts,
                task_attempt_scorecard=task_scorecard,
                predictions=predictions,
                runtime_instances=runtime_instances,
                benchmark_plan=benchmark_plan,
                readiness_gate=readiness_gate.summary,
                skipped=[
                    "benchmark-launcher",
                    "benchmark-launch",
                    "benchmark-collect-grading",
                    "benchmark-scorecard",
                ],
                logbook_dir=logbook_dir,
            ),
        )

    launcher_handoff = write_benchmark_launcher_handoff(
        logbook_dir=logbook_dir,
        max_workers=max_workers,
        python_executable=python_executable,
    )
    benchmark_launch = write_benchmark_launch_result(
        logbook_dir=logbook_dir,
        command_runner=benchmark_command_runner,
    )
    grading_collection = collect_benchmark_grading_reports(
        config_path=config_path,
        logbook_dir=logbook_dir,
    )
    if int(grading_collection["summary"]["collected_reports"]) == 0:
        return _write_summary(
            logbook_dir,
            _blocked_summary(
                regatta=regatta.name,
                course=regatta.course.name,
                course_handoff=course_handoff,
                preflight=preflight,
                preflight_evidence_report=preflight_evidence_report,
                attempts=attempts,
                task_attempt_scorecard=task_scorecard,
                predictions=predictions,
                runtime_instances=runtime_instances,
                benchmark_plan=benchmark_plan,
                readiness_gate=readiness_gate.summary,
                launcher_handoff=launcher_handoff,
                benchmark_launch=benchmark_launch,
                grading_collection=grading_collection,
                skipped=["benchmark-scorecard"],
                logbook_dir=logbook_dir,
            ),
        )
    scorecard = write_benchmark_scorecard(logbook_dir)
    return _write_summary(
        logbook_dir,
        {
            "status": scorecard["status"],
            "regatta": scorecard["regatta"],
            "course": scorecard["course"],
            "agent": "pi",
            "course_handoff": course_handoff,
            "preflight": preflight,
            "preflight_evidence_report": preflight_evidence_report,
            "attempts": attempts,
            "task_attempt_scorecard": task_scorecard,
            "predictions": predictions,
            "runtime_instances": runtime_instances,
            "benchmark_plan": benchmark_plan,
            "readiness_gate": readiness_gate.summary,
            "launcher_handoff": launcher_handoff,
            "benchmark_launch": benchmark_launch,
            "grading_collection": grading_collection,
            "scorecard": scorecard,
            "next_steps": scorecard["next_steps"],
            "artifacts": _artifacts(logbook_dir),
        },
    )


def _blocked_summary(
    *,
    regatta: str,
    course: str,
    course_handoff: dict[str, Any],
    preflight: dict[str, Any],
    preflight_evidence_report: dict[str, Any],
    skipped: list[str],
    logbook_dir: Path,
    attempts: dict[str, Any] | None = None,
    task_attempt_scorecard: dict[str, Any] | None = None,
    predictions: list[dict[str, Any]] | None = None,
    runtime_instances: dict[str, Any] | None = None,
    benchmark_plan: dict[str, Any] | None = None,
    readiness_gate: dict[str, Any] | None = None,
    launcher_handoff: dict[str, Any] | None = None,
    benchmark_launch: dict[str, Any] | None = None,
    grading_collection: dict[str, Any] | None = None,
    failed_stage: str | None = None,
    error: str | None = None,
    next_steps: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "blocked",
        "regatta": regatta,
        "course": course,
        "agent": "pi",
        "course_handoff": course_handoff,
        "preflight": preflight,
        "preflight_evidence_report": preflight_evidence_report,
        "skipped": skipped,
        "artifacts": _artifacts(logbook_dir),
    }
    if failed_stage is not None:
        summary["failed_stage"] = failed_stage
    if error is not None:
        summary["error"] = error
    for key, value in (
        ("attempts", attempts),
        ("task_attempt_scorecard", task_attempt_scorecard),
        ("predictions", predictions),
        ("runtime_instances", runtime_instances),
        ("benchmark_plan", benchmark_plan),
        ("readiness_gate", readiness_gate),
        ("launcher_handoff", launcher_handoff),
        ("benchmark_launch", benchmark_launch),
        ("grading_collection", grading_collection),
    ):
        if value is not None:
            summary[key] = value
    if next_steps is not None:
        summary["next_steps"] = next_steps
        return summary
    for value in (grading_collection, benchmark_launch):
        if isinstance(value, dict) and "next_steps" in value:
            summary["next_steps"] = value["next_steps"]
            break
    return summary


def _prediction_failure_next_steps(logbook_dir: Path) -> list[dict[str, object]]:
    return [
        command_step(
            label="Inspect task attempts",
            reason=(
                "At least one completed task attempt could not be converted into "
                "a SWE-bench candidate patch. Inspect the task attempt artifacts "
                "listed in the task attempt scorecard, then rerun the benchmark."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "task-attempt-scorecard",
                "--logbook",
                str(logbook_dir),
            ],
        ),
        command_step(
            label="Rerun real benchmark eval",
            reason=(
                "Candidate patch extraction depends on stochastic agent output; "
                "rerun after inspecting the failed attempt response."
            ),
            command=[
                "uv",
                "run",
                "yacht",
                "real-benchmark-eval",
                "<regatta.toml>",
                "--logbook",
                str(logbook_dir),
                "--workspace",
                ".",
            ],
        ),
    ]


def _artifacts(logbook_dir: Path) -> dict[str, str]:
    return {
        "logbook": str(logbook_dir),
        "real_benchmark_eval": str(logbook_dir / REAL_BENCHMARK_EVAL_PATH),
        "preflight_evidence_report": str(logbook_dir / PREFLIGHT_EVIDENCE_REPORT_PATH),
        "runtime_instances": str(logbook_dir / RUNTIME_INSTANCES_PLAN_PATH),
        "task_attempt_scorecard": str(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH),
        "benchmark_execution_plan": str(logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH),
        "benchmark_launcher_handoff": str(logbook_dir / BENCHMARK_LAUNCHER_HANDOFF_PATH),
        "benchmark_launch_result": str(logbook_dir / BENCHMARK_LAUNCH_RESULT_PATH),
        "benchmark_grading_collection": str(
            logbook_dir / BENCHMARK_GRADING_COLLECTION_PATH
        ),
        "benchmark_scorecard": str(logbook_dir / BENCHMARK_SCORECARD_PATH),
    }


def _write_summary(logbook_dir: Path, summary: dict[str, Any]) -> dict[str, Any]:
    path = logbook_dir / REAL_BENCHMARK_EVAL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
