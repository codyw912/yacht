import tempfile
import unittest
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.courses.registry import benchmark_adapter
from yacht.courses.registry import course_adapter
from yacht.courses.registry import evaluator_adapter
from yacht.courses.registry import supported_benchmark_adapter_kinds
from yacht.courses.registry import supported_course_adapter_harnesses
from yacht.domain.model import ConfigError, Task, load_regatta


class BenchmarkAdapterRegistryTests(unittest.TestCase):
    def test_exposes_separate_course_and_evaluator_adapters(self) -> None:
        course = course_adapter("swe-bench")
        evaluator = evaluator_adapter("swe-bench")
        benchmark = benchmark_adapter("swe-bench")

        self.assertEqual(course.kind, "swe-bench")
        self.assertEqual(course.display_name, "SWE-bench")
        self.assertEqual(course.supported_harnesses, ("docker",))
        self.assertIn("candidate_patches", course.expected_outputs())
        self.assertEqual(evaluator.kind, "swe-bench")
        self.assertEqual(evaluator.display_name, "SWE-bench")
        self.assertEqual(evaluator.grading_schema, "yacht.swe-bench-grading.v1")
        self.assertEqual(benchmark.kind, "swe-bench")
        self.assertEqual(benchmark.course, course)
        self.assertEqual(benchmark.evaluator, evaluator)

    def test_exposes_supported_benchmark_adapter_metadata(self) -> None:
        self.assertEqual(
            supported_benchmark_adapter_kinds(),
            ("custom-eval", "swe-bench"),
        )
        self.assertEqual(supported_course_adapter_harnesses(), ("docker", "local"))
        self.assertEqual(supported_course_adapter_harnesses("swe-bench"), ("docker",))

        adapter = benchmark_adapter("swe-bench")

        self.assertEqual(adapter.kind, "swe-bench")
        self.assertEqual(adapter.display_name, "SWE-bench")
        self.assertEqual(adapter.grading_schema, "yacht.swe-bench-grading.v1")
        self.assertEqual(
            adapter.expected_outputs(),
            {
                "candidate_patches": "course-handoff/swe-bench/candidate-patches.jsonl",
                "grading_report": "course-handoff/swe-bench/grading-report.json",
            },
        )
        self.assertEqual(
            adapter.grading("docker"),
            {
                "delegated_to": "swe-bench",
                "execution": "docker-harness",
                "status": "planned",
            },
        )

    def test_exposes_custom_eval_adapter_metadata(self) -> None:
        adapter = benchmark_adapter("custom-eval")

        self.assertEqual(adapter.kind, "custom-eval")
        self.assertEqual(adapter.display_name, "Custom eval")
        self.assertEqual(adapter.supported_harnesses, ("local",))
        self.assertEqual(adapter.grading_schema, "yacht.custom-eval-grading.v1")
        self.assertEqual(
            adapter.expected_outputs(),
            {
                "candidate_patches": "course-handoff/custom-eval/candidate-patches.jsonl",
                "grading_report": "course-handoff/custom-eval/grading-report.json",
            },
        )
        self.assertEqual(
            adapter.grading("local"),
            {
                "delegated_to": "custom-eval",
                "execution": "local-harness",
                "status": "planned",
            },
        )

    def test_builds_custom_eval_launcher_command(self) -> None:
        adapter = benchmark_adapter("custom-eval")

        command = adapter.launcher_command(
            course_adapter={
                "kind": "custom-eval",
                "dataset": "local",
                "split": "smoke",
                "harness": "local",
            },
            tasks=[{"id": "local-smoke-1"}],
            candidate_path=Path("/tmp/candidate-patches.jsonl"),
            native_report_dir=Path("/tmp/native-report"),
            run_id="run-1",
            max_workers=1,
            python_command=["ignored"],
        )

        self.assertEqual(
            command,
            [
                "uv",
                "run",
                "python",
                "-m",
                "yacht.courses.custom_eval.harness",
                "--candidate-records",
                "/tmp/candidate-patches.jsonl",
                "--report-dir",
                "/tmp/native-report",
                "--run-id",
                "run-1",
            ],
        )

    def test_builds_swe_bench_launcher_command(self) -> None:
        adapter = benchmark_adapter("swe-bench")

        command = adapter.launcher_command(
            course_adapter={
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
                "harness": "docker",
            },
            tasks=[
                {"id": "django__django-11099"},
                {"id": "django__django-11179"},
            ],
            candidate_path=Path("/tmp/candidate-patches.jsonl"),
            native_report_dir=Path("/tmp/native-report"),
            run_id="run-1",
            max_workers=2,
            python_command=["uv", "run", "python"],
        )

        self.assertEqual(
            command,
            [
                "uv",
                "run",
                "python",
                "-m",
                "swebench.harness.run_evaluation",
                "--dataset_name",
                "princeton-nlp/SWE-bench_Lite",
                "--split",
                "test",
                "--predictions_path",
                "/tmp/candidate-patches.jsonl",
                "--max_workers",
                "2",
                "--run_id",
                "run-1",
                "--report_dir",
                "/tmp/native-report",
                "--instance_ids",
                "django__django-11099",
                "django__django-11179",
            ],
        )

    def test_swe_bench_prompt_instructions_are_adapter_owned(self) -> None:
        task = Task(
            id="django__django-11099",
            title="Fix a regression",
            difficulty=1,
            repo="django/django",
            base_commit="abc123",
            problem_statement="Problem details",
        )

        instructions = benchmark_adapter("swe-bench").task_prompt_instructions(task)

        self.assertIn("SWE-bench submission instructions", instructions)
        self.assertIn("model_patch", instructions)
        self.assertIn("Problem details", instructions)
        self.assertIn("repo: django/django", instructions)
        self.assertIn("base_commit: abc123", instructions)

    def test_custom_eval_prompt_instructions_include_expected_response_fields(
        self,
    ) -> None:
        task = Task(
            id="custom-1",
            title="Complete custom task",
            difficulty=1,
            problem_statement="Return the expected fields.",
            expect_response={"completed": True, "quality": "accepted"},
            expect_tool_calls=("repo-map",),
        )

        instructions = benchmark_adapter("custom-eval").task_prompt_instructions(task)

        self.assertIn("Custom eval submission instructions", instructions)
        self.assertIn("completed=True", instructions)
        self.assertIn("quality='accepted'", instructions)
        self.assertIn("repo-map", instructions)
        self.assertIn("Return the expected fields.", instructions)

    def test_rejects_unknown_benchmark_adapter(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "unsupported benchmark adapter custom"
        ):
            benchmark_adapter("custom")

    def test_course_adapter_harness_is_validated_per_adapter_kind(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace('harness = "docker"', 'harness = "local"')
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "course.adapter.harness must be one of: docker",
            ):
                load_regatta(config_path)

        custom_config = PI_WITH_FFF_CONFIG.replace(
            'kind = "swe-bench"',
            'kind = "custom-eval"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(custom_config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "course.adapter.harness must be one of: local",
            ):
                load_regatta(config_path)


if __name__ == "__main__":
    unittest.main()
