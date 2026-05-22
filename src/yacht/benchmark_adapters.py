from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class BenchmarkAdapter(Protocol):
    kind: str
    display_name: str
    supported_harnesses: tuple[str, ...]
    grading_schema: str

    def expected_outputs(self) -> dict[str, str]:
        ...

    def grading(self, harness: str) -> dict[str, str]:
        ...

    def task_prompt_instructions(self, task: Any) -> str:
        ...

    def task_with_context(self, *, task: Any, adapter: Any) -> Any:
        ...

    def workspace_for_attempt(
        self,
        *,
        task: Any,
        workspace_path: Path,
        workspace_root: Path,
        comparison_name: str,
        vessel_name: str,
    ) -> Path:
        ...

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]:
        ...

    def native_report_filename(self, *, vessel_name: str, run_id: str) -> str:
        ...

    def write_grading_report(
        self,
        *,
        config_path: Path,
        native_report_path: Path,
        logbook_dir: Path,
        vessel_name: str,
    ) -> dict[str, Any]:
        ...

    def write_predictions_from_attempts(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class SweBenchAdapter:
    kind: str = "swe-bench"
    display_name: str = "SWE-bench"
    supported_harnesses: tuple[str, ...] = ("docker",)
    grading_schema: str = "yacht.swe-bench-grading.v1"

    def expected_outputs(self) -> dict[str, str]:
        return {
            "candidate_patches": "course-handoff/swe-bench/candidate-patches.jsonl",
            "grading_report": "course-handoff/swe-bench/grading-report.json",
        }

    def grading(self, harness: str) -> dict[str, str]:
        return {
            "delegated_to": self.kind,
            "execution": f"{harness}-harness",
            "status": "planned",
        }

    def task_prompt_instructions(self, task: Any) -> str:
        prompt = "\nSWE-bench submission instructions:\n"
        prompt += (
            "When finished, respond with a JSON object containing a non-empty "
            "model_patch string. model_patch must be a unified diff candidate patch "
            "for this task. Do not wrap the JSON in markdown fences.\n"
        )
        if task.problem_statement is not None:
            prompt += f"\nProblem statement:\n{task.problem_statement}\n"
        if task.repo is not None and task.base_commit is not None:
            prompt += (
                "\nRepository context:\n"
                f"- repo: {task.repo}\n"
                f"- base_commit: {task.base_commit}\n"
            )
        return prompt

    def task_with_context(self, *, task: Any, adapter: Any) -> Any:
        from yacht.swebench_task_context import task_with_swe_bench_context

        return task_with_swe_bench_context(task=task, adapter=adapter)

    def workspace_for_attempt(
        self,
        *,
        task: Any,
        workspace_path: Path,
        workspace_root: Path,
        comparison_name: str,
        vessel_name: str,
    ) -> Path:
        from yacht.swebench_task_context import materialize_swe_bench_workspace

        return materialize_swe_bench_workspace(
            task=task,
            workspace_root=workspace_root,
            comparison_name=comparison_name,
            vessel_name=vessel_name,
        )

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]:
        return [
            *python_command,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            str(course_adapter["dataset"]),
            "--split",
            str(course_adapter["split"]),
            "--predictions_path",
            str(candidate_path),
            "--max_workers",
            str(max_workers),
            "--run_id",
            run_id,
            "--report_dir",
            str(native_report_dir),
            "--instance_ids",
            *[str(task["id"]) for task in tasks],
        ]

    def native_report_filename(self, *, vessel_name: str, run_id: str) -> str:
        return f"{vessel_name}.{run_id}.json"

    def write_grading_report(
        self,
        *,
        config_path: Path,
        native_report_path: Path,
        logbook_dir: Path,
        vessel_name: str,
    ) -> dict[str, Any]:
        from yacht.swebench_grading import write_swe_bench_grading_report

        return write_swe_bench_grading_report(
            config_path=config_path,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )

    def write_predictions_from_attempts(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        from yacht.swebench_predictions_from_attempts import (
            write_swe_bench_predictions_from_attempts,
        )

        return write_swe_bench_predictions_from_attempts(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )


@dataclass(frozen=True)
class CustomEvalAdapter:
    kind: str = "custom-eval"
    display_name: str = "Custom eval"
    supported_harnesses: tuple[str, ...] = ("local",)
    grading_schema: str = "yacht.custom-eval-grading.v1"

    def expected_outputs(self) -> dict[str, str]:
        return {
            "candidate_patches": "course-handoff/custom-eval/candidate-patches.jsonl",
            "grading_report": "course-handoff/custom-eval/grading-report.json",
        }

    def grading(self, harness: str) -> dict[str, str]:
        return {
            "delegated_to": self.kind,
            "execution": f"{harness}-harness",
            "status": "planned",
        }

    def task_prompt_instructions(self, task: Any) -> str:
        prompt = "\nCustom eval submission instructions:\n"
        prompt += (
            "When finished, respond with a JSON object containing completed as a "
            "boolean. Do not wrap the JSON in markdown fences.\n"
        )
        if task.problem_statement is not None:
            prompt += f"\nProblem statement:\n{task.problem_statement}\n"
        return prompt

    def task_with_context(self, *, task: Any, adapter: Any) -> Any:
        return task

    def workspace_for_attempt(
        self,
        *,
        task: Any,
        workspace_path: Path,
        workspace_root: Path,
        comparison_name: str,
        vessel_name: str,
    ) -> Path:
        return workspace_path

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]:
        return [
            "uv",
            "run",
            "python",
            "-m",
            "yacht.custom_eval_harness",
            "--candidate-records",
            str(candidate_path),
            "--report-dir",
            str(native_report_dir),
            "--run-id",
            run_id,
        ]

    def native_report_filename(self, *, vessel_name: str, run_id: str) -> str:
        return f"{vessel_name}.{run_id}.json"

    def write_grading_report(
        self,
        *,
        config_path: Path,
        native_report_path: Path,
        logbook_dir: Path,
        vessel_name: str,
    ) -> dict[str, Any]:
        from yacht.custom_eval_grading import write_custom_eval_grading_report

        return write_custom_eval_grading_report(
            config_path=config_path,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )

    def write_predictions_from_attempts(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        from yacht.custom_eval_predictions_from_attempts import (
            write_custom_eval_predictions_from_attempts,
        )

        return write_custom_eval_predictions_from_attempts(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )


_BENCHMARK_ADAPTERS: dict[str, BenchmarkAdapter] = {
    "custom-eval": CustomEvalAdapter(),
    "swe-bench": SweBenchAdapter(),
}


def benchmark_adapter(kind: str) -> BenchmarkAdapter:
    try:
        return _BENCHMARK_ADAPTERS[kind]
    except KeyError as error:
        from yacht.regatta import ConfigError

        raise ConfigError(f"unsupported benchmark adapter {kind}") from error


def supported_benchmark_adapter_kinds() -> tuple[str, ...]:
    return tuple(sorted(_BENCHMARK_ADAPTERS))


def supported_course_adapter_harnesses(kind: str | None = None) -> tuple[str, ...]:
    if kind is not None:
        return benchmark_adapter(kind).supported_harnesses
    return tuple(
        sorted(
            {
                harness
                for adapter in _BENCHMARK_ADAPTERS.values()
                for harness in adapter.supported_harnesses
            }
        )
    )


def course_adapter_to_json(adapter: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": adapter.kind,
        "dataset": adapter.dataset,
        "split": adapter.split,
        "harness": adapter.harness,
    }
    if adapter.instance_ids:
        payload["instance_ids"] = list(adapter.instance_ids)
    return payload


def course_adapter_summary(adapter: Any) -> dict[str, Any]:
    return {
        "kind": adapter.kind,
        "dataset": adapter.dataset,
        "split": adapter.split,
        "harness": adapter.harness,
    }


def command_preview(command: list[str]) -> str:
    return shlex.join(command)
