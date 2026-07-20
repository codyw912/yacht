from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class CourseAdapterInterface(Protocol):
    kind: str
    display_name: str
    supported_harnesses: tuple[str, ...]
    native_rollout: bool

    def expected_outputs(self) -> dict[str, str]: ...

    def task_prompt_instructions(self, task: Any) -> str: ...

    def task_with_context(self, *, task: Any, adapter: Any) -> Any: ...

    def workspace_for_attempt(
        self,
        *,
        task: Any,
        workspace_path: Path,
        workspace_root: Path,
        comparison_name: str,
        vessel_name: str,
    ) -> Path: ...

    def write_predictions_from_attempts(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]: ...

    def write_attempts_from_native_rollout(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]: ...


class EvaluatorAdapterInterface(Protocol):
    kind: str
    display_name: str
    grading_schema: str

    def grading(self, harness: str) -> dict[str, str]: ...

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        vessel_name: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]: ...

    def native_report_filename(self, *, vessel_name: str, run_id: str) -> str: ...

    def write_grading_report(
        self,
        *,
        config_path: Path,
        native_report_path: Path,
        logbook_dir: Path,
        vessel_name: str,
    ) -> dict[str, Any]: ...


class BenchmarkAdapter(
    CourseAdapterInterface,
    EvaluatorAdapterInterface,
    Protocol,
):
    course: CourseAdapterInterface
    evaluator: EvaluatorAdapterInterface


@dataclass(frozen=True)
class BenchmarkAdapterFacade:
    course: CourseAdapterInterface
    evaluator: EvaluatorAdapterInterface

    @property
    def kind(self) -> str:
        return self.course.kind

    @property
    def display_name(self) -> str:
        return self.course.display_name

    @property
    def supported_harnesses(self) -> tuple[str, ...]:
        return self.course.supported_harnesses

    @property
    def native_rollout(self) -> bool:
        return self.course.native_rollout

    @property
    def grading_schema(self) -> str:
        return self.evaluator.grading_schema

    def expected_outputs(self) -> dict[str, str]:
        return self.course.expected_outputs()

    def grading(self, harness: str) -> dict[str, str]:
        return self.evaluator.grading(harness)

    def task_prompt_instructions(self, task: Any) -> str:
        return self.course.task_prompt_instructions(task)

    def task_with_context(self, *, task: Any, adapter: Any) -> Any:
        return self.course.task_with_context(task=task, adapter=adapter)

    def workspace_for_attempt(
        self,
        *,
        task: Any,
        workspace_path: Path,
        workspace_root: Path,
        comparison_name: str,
        vessel_name: str,
    ) -> Path:
        return self.course.workspace_for_attempt(
            task=task,
            workspace_path=workspace_path,
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
        vessel_name: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]:
        return self.evaluator.launcher_command(
            course_adapter=course_adapter,
            tasks=tasks,
            candidate_path=candidate_path,
            native_report_dir=native_report_dir,
            run_id=run_id,
            vessel_name=vessel_name,
            max_workers=max_workers,
            python_command=python_command,
        )

    def native_report_filename(self, *, vessel_name: str, run_id: str) -> str:
        return self.evaluator.native_report_filename(
            vessel_name=vessel_name,
            run_id=run_id,
        )

    def write_grading_report(
        self,
        *,
        config_path: Path,
        native_report_path: Path,
        logbook_dir: Path,
        vessel_name: str,
    ) -> dict[str, Any]:
        return self.evaluator.write_grading_report(
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
        return self.course.write_predictions_from_attempts(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )

    def write_attempts_from_native_rollout(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        return self.course.write_attempts_from_native_rollout(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )


@dataclass(frozen=True)
class SweBenchCourseAdapter:
    kind: str = "swe-bench"
    display_name: str = "SWE-bench"
    supported_harnesses: tuple[str, ...] = ("docker",)
    native_rollout: bool = False

    def expected_outputs(self) -> dict[str, str]:
        return {
            "candidate_patches": "course-handoff/swe-bench/candidate-patches.jsonl",
            "grading_report": "course-handoff/swe-bench/grading-report.json",
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
        from yacht.courses.swe_bench.task_context import task_with_swe_bench_context

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
        from yacht.courses.swe_bench.task_context import materialize_swe_bench_workspace

        return materialize_swe_bench_workspace(
            task=task,
            workspace_root=workspace_root,
            comparison_name=comparison_name,
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
        from yacht.courses.swe_bench.predictions_from_attempts import (
            write_swe_bench_predictions_from_attempts,
        )

        return write_swe_bench_predictions_from_attempts(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )

    def write_attempts_from_native_rollout(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        raise _no_native_rollout(self.kind)


@dataclass(frozen=True)
class SweBenchEvaluatorAdapter:
    kind: str = "swe-bench"
    display_name: str = "SWE-bench"
    grading_schema: str = "yacht.swe-bench-grading.v1"

    def grading(self, harness: str) -> dict[str, str]:
        return {
            "delegated_to": self.kind,
            "execution": f"{harness}-harness",
            "status": "planned",
        }

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        vessel_name: str,
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
        from yacht.courses.swe_bench.grading import write_swe_bench_grading_report

        return write_swe_bench_grading_report(
            config_path=config_path,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )


@dataclass(frozen=True)
class CustomEvalCourseAdapter:
    kind: str = "custom-eval"
    display_name: str = "Custom eval"
    supported_harnesses: tuple[str, ...] = ("local",)
    native_rollout: bool = False

    def expected_outputs(self) -> dict[str, str]:
        return {
            "candidate_patches": "course-handoff/custom-eval/candidate-patches.jsonl",
            "grading_report": "course-handoff/custom-eval/grading-report.json",
        }

    def task_prompt_instructions(self, task: Any) -> str:
        prompt = "\nCustom eval submission instructions:\n"
        expected = task.expect_response or {"completed": True}
        fields = ", ".join(
            f"{key}={value!r}" for key, value in sorted(expected.items())
        )
        prompt += (
            "When finished, respond with a JSON object matching these expected "
            f"top-level fields: {fields}. Do not wrap the JSON in markdown fences.\n"
        )
        if task.expect_tool_calls:
            tools = ", ".join(sorted(task.expect_tool_calls))
            prompt += f"Expected tool-call evidence: {tools}.\n"
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

    def write_predictions_from_attempts(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        from yacht.courses.custom_eval.predictions_from_attempts import (
            write_custom_eval_predictions_from_attempts,
        )

        return write_custom_eval_predictions_from_attempts(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )

    def write_attempts_from_native_rollout(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        raise _no_native_rollout(self.kind)


@dataclass(frozen=True)
class CustomEvalEvaluatorAdapter:
    kind: str = "custom-eval"
    display_name: str = "Custom eval"
    grading_schema: str = "yacht.custom-eval-grading.v1"

    def grading(self, harness: str) -> dict[str, str]:
        return {
            "delegated_to": self.kind,
            "execution": f"{harness}-harness",
            "status": "planned",
        }

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        vessel_name: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]:
        return [
            "uv",
            "run",
            "python",
            "-m",
            "yacht.courses.custom_eval.harness",
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
        from yacht.courses.custom_eval.grading import write_custom_eval_grading_report

        return write_custom_eval_grading_report(
            config_path=config_path,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )


@dataclass(frozen=True)
class TerminalBenchCourseAdapter:
    kind: str = "terminal-bench"
    display_name: str = "Terminal-Bench"
    supported_harnesses: tuple[str, ...] = ("harbor",)
    native_rollout: bool = True

    def expected_outputs(self) -> dict[str, str]:
        return {
            "candidate_patches": (
                "course-handoff/terminal-bench/candidate-patches.jsonl"
            ),
            "grading_report": "course-handoff/terminal-bench/grading-report.json",
        }

    def task_prompt_instructions(self, task: Any) -> str:
        return (
            "\nTerminal-Bench tasks are rolled out natively by the Harbor "
            "harness; yacht does not prompt the agent directly.\n"
        )

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

    def write_predictions_from_attempts(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        from yacht.courses.terminal_bench.rollout_plan import (
            write_terminal_bench_rollout_plan,
        )

        return write_terminal_bench_rollout_plan(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )

    def write_attempts_from_native_rollout(
        self,
        *,
        config_path: Path,
        logbook_dir: Path,
        vessel_name: str,
        comparison_name: str | None = None,
    ) -> dict[str, Any]:
        from yacht.courses.terminal_bench.attempts_from_trials import (
            write_terminal_bench_attempts_from_trials,
        )

        return write_terminal_bench_attempts_from_trials(
            config_path=config_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
            comparison_name=comparison_name,
        )


@dataclass(frozen=True)
class TerminalBenchEvaluatorAdapter:
    kind: str = "terminal-bench"
    display_name: str = "Terminal-Bench"
    grading_schema: str = "yacht.terminal-bench-grading.v1"

    def grading(self, harness: str) -> dict[str, str]:
        return {
            "delegated_to": self.kind,
            "execution": f"{harness}-harness",
            "status": "planned",
        }

    def launcher_command(
        self,
        *,
        course_adapter: dict[str, Any],
        tasks: list[dict[str, Any]],
        candidate_path: Path,
        native_report_dir: Path,
        run_id: str,
        vessel_name: str,
        max_workers: int,
        python_command: list[str],
    ) -> list[str]:
        from yacht.courses.terminal_bench.job import TERMINAL_BENCH_JOB_FILENAME

        vessel_dir = candidate_path.parent
        return [
            "uv",
            "run",
            "python",
            "-m",
            "yacht.courses.terminal_bench.harness",
            "--job",
            str(vessel_dir / TERMINAL_BENCH_JOB_FILENAME),
            "--roster",
            str(candidate_path),
            "--trials-dir",
            str(vessel_dir / "harbor-trials"),
            "--report-dir",
            str(native_report_dir),
            "--run-id",
            run_id,
            "--vessel",
            vessel_name,
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
        from yacht.courses.terminal_bench.grading import (
            write_terminal_bench_grading_report,
        )

        return write_terminal_bench_grading_report(
            config_path=config_path,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name=vessel_name,
        )


def _no_native_rollout(kind: str) -> Exception:
    from yacht.domain.model import ConfigError

    return ConfigError(
        f"course adapter {kind} does not synthesize attempts from a native rollout"
    )


SweBenchAdapter = SweBenchCourseAdapter
CustomEvalAdapter = CustomEvalCourseAdapter


_COURSE_ADAPTERS: dict[str, CourseAdapterInterface] = {
    "custom-eval": CustomEvalCourseAdapter(),
    "swe-bench": SweBenchCourseAdapter(),
    "terminal-bench": TerminalBenchCourseAdapter(),
}

_EVALUATOR_ADAPTERS: dict[str, EvaluatorAdapterInterface] = {
    "custom-eval": CustomEvalEvaluatorAdapter(),
    "swe-bench": SweBenchEvaluatorAdapter(),
    "terminal-bench": TerminalBenchEvaluatorAdapter(),
}

_BENCHMARK_ADAPTERS: dict[str, BenchmarkAdapterFacade] = {
    kind: BenchmarkAdapterFacade(
        course=course,
        evaluator=_EVALUATOR_ADAPTERS[kind],
    )
    for kind, course in _COURSE_ADAPTERS.items()
}


def benchmark_adapter(kind: str) -> BenchmarkAdapter:
    try:
        return _BENCHMARK_ADAPTERS[kind]
    except KeyError as error:
        from yacht.domain.model import ConfigError

        raise ConfigError(f"unsupported benchmark adapter {kind}") from error


def course_adapter(kind: str) -> CourseAdapterInterface:
    try:
        return _COURSE_ADAPTERS[kind]
    except KeyError as error:
        from yacht.domain.model import ConfigError

        raise ConfigError(f"unsupported course adapter {kind}") from error


def evaluator_adapter(kind: str) -> EvaluatorAdapterInterface:
    try:
        return _EVALUATOR_ADAPTERS[kind]
    except KeyError as error:
        from yacht.domain.model import ConfigError

        raise ConfigError(f"unsupported evaluator adapter {kind}") from error


def supported_benchmark_adapter_kinds() -> tuple[str, ...]:
    return tuple(sorted(_BENCHMARK_ADAPTERS))


def supported_course_adapter_harnesses(kind: str | None = None) -> tuple[str, ...]:
    if kind is not None:
        return course_adapter(kind).supported_harnesses
    return tuple(
        sorted(
            {
                harness
                for adapter in _COURSE_ADAPTERS.values()
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
