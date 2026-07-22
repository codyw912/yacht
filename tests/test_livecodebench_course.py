import json
import tempfile
import unittest
from pathlib import Path

from yacht.courses.registry import benchmark_adapter
from yacht.courses.livecodebench import task_context
from yacht.courses.livecodebench.task_context import (
    dump_command,
    task_with_livecodebench_context,
    window_question_ids,
)
from yacht.domain.model import ConfigError, CourseAdapter, Task, load_regatta


LIVECODEBENCH_CONFIG = """
[regatta]
name = "lcb-window-smoke"

[preflight]
failure_policy = "abort-group"

[course]
name = "livecodebench-lite"

[course.adapter]
kind = "livecodebench"
dataset = "livecodebench/code_generation_lite"
split = "release_v1"
harness = "docker"
instance_ids = ["abc301_a", "abc301_b"]
start_date = "2023-05-01"
end_date = "2023-05-14"

[runtimes.claude-runtime]
backend = "container"
harness = "claude-code"
image = "yacht/claude-code-runtime:claude-code-2.1.211"
command = ["claude"]

[runtimes.claude-runtime.preflight]
required = true
checks = [
  { name = "docker-daemon", kind = "command", command = ["docker", "info"] },
]

[[vessels]]
name = "claude-baseline"
model = "claude-haiku-4-5"
runtime = "claude-runtime"

[[vessels]]
name = "claude-challenger"
model = "claude-haiku-4-5"
runtime = "claude-runtime"

[[comparisons]]
name = "lcb-baseline-vs-challenger"
course = "livecodebench-lite"
vessels = ["claude-baseline", "claude-challenger"]
"""


def _adapter(**overrides) -> CourseAdapter:
    fields = {
        "kind": "livecodebench",
        "dataset": "livecodebench/code_generation_lite",
        "split": "release_v1",
        "harness": "docker",
        "instance_ids": ("abc301_a",),
        "start_date": "2023-05-01",
        "end_date": "2023-05-14",
    }
    fields.update(overrides)
    return CourseAdapter(**fields)


def _fake_dump(problems: list[dict]) -> callable:
    def runner(command):
        return json.dumps(problems) + "\n"

    return runner


def _clear_window_cache() -> None:
    task_context._WINDOW_CACHE.clear()


class LiveCodeBenchConfigTests(unittest.TestCase):
    def test_parses_window_and_synthesizes_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(LIVECODEBENCH_CONFIG, encoding="utf-8")

            regatta = load_regatta(config_path)

            adapter = regatta.course.adapter
            self.assertEqual(adapter.start_date, "2023-05-01")
            self.assertEqual(adapter.end_date, "2023-05-14")
            self.assertEqual(
                [task.id for task in regatta.course.tasks],
                ["abc301_a", "abc301_b"],
            )
            self.assertEqual(
                regatta.course.tasks[0].title,
                "livecodebench instance abc301_a",
            )

    def test_requires_the_contest_date_window(self) -> None:
        config = LIVECODEBENCH_CONFIG.replace('start_date = "2023-05-01"\n', "")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "requires start_date and end_date"):
                load_regatta(config_path)

    def test_rejects_malformed_dates_and_inverted_windows(self) -> None:
        bad_format = LIVECODEBENCH_CONFIG.replace(
            'start_date = "2023-05-01"', 'start_date = "May 1 2023"'
        )
        inverted = LIVECODEBENCH_CONFIG.replace(
            'start_date = "2023-05-01"', 'start_date = "2023-06-01"'
        )
        for config, message in (
            (bad_format, "YYYY-MM-DD"),
            (inverted, "must not be after"),
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / "regatta.toml"
                config_path.write_text(config, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    load_regatta(config_path)


class LiveCodeBenchTaskContextTests(unittest.TestCase):
    def setUp(self) -> None:
        _clear_window_cache()

    def tearDown(self) -> None:
        _clear_window_cache()

    def test_fills_problem_statement_from_window_dump(self) -> None:
        task = Task(id="abc301_a", title="lcb instance", difficulty=1)
        dump = _fake_dump(
            [
                {
                    "question_id": "abc301_a",
                    "title": "Overall Winner",
                    "content": "Takahashi and Aoki played N games...",
                    "starter_code": "",
                    "platform": "atcoder",
                    "contest_date": "2023-05-13T00:00:00",
                }
            ]
        )

        contexted = task_with_livecodebench_context(
            task=task,
            adapter=_adapter(),
            dump_runner=dump,
        )

        self.assertIn("Overall Winner", contexted.problem_statement)
        self.assertIn("Takahashi", contexted.problem_statement)
        self.assertNotIn("Starter code", contexted.problem_statement)

    def test_includes_starter_code_when_present(self) -> None:
        task = Task(id="2727", title="lcb instance", difficulty=1)
        dump = _fake_dump(
            [
                {
                    "question_id": "2727",
                    "title": "Number of Senior Citizens",
                    "content": "You are given...",
                    "starter_code": "class Solution:\n    def f(self): ...",
                    "platform": "leetcode",
                    "contest_date": "2023-05-06T00:00:00",
                }
            ]
        )

        contexted = task_with_livecodebench_context(
            task=task,
            adapter=_adapter(instance_ids=("2727",)),
            dump_runner=dump,
        )

        self.assertIn("Starter code:", contexted.problem_statement)
        self.assertIn("class Solution:", contexted.problem_statement)

    def test_rejects_tasks_outside_the_window(self) -> None:
        task = Task(id="not-in-window", title="lcb instance", difficulty=1)
        dump = _fake_dump(
            [
                {
                    "question_id": "abc301_a",
                    "title": "t",
                    "content": "c",
                    "starter_code": "",
                    "platform": "atcoder",
                    "contest_date": "2023-05-13T00:00:00",
                }
            ]
        )

        with self.assertRaisesRegex(ConfigError, "not in the livecodebench window"):
            task_with_livecodebench_context(
                task=task,
                adapter=_adapter(),
                dump_runner=dump,
            )

    def test_window_ids_are_sorted_and_cached(self) -> None:
        calls = []

        def dump(command):
            calls.append(command)
            return json.dumps(
                [
                    {"question_id": "b", "title": "t", "content": "c"},
                    {"question_id": "a", "title": "t", "content": "c"},
                ]
            )

        adapter = _adapter()
        first = window_question_ids(adapter, dump_runner=dump)
        second = window_question_ids(adapter, dump_runner=dump)

        self.assertEqual(first, ["a", "b"])
        self.assertEqual(second, ["a", "b"])
        self.assertEqual(len(calls), 1)

    def test_dump_command_targets_pinned_image(self) -> None:
        command = dump_command(_adapter())

        self.assertEqual(command[:3], ["docker", "run", "--rm"])
        self.assertIn("yacht/lcb-runner:lcb-28fef95", command)
        self.assertEqual(command[-3:], ["release_v1", "2023-05-01", "2023-05-14"])


class LiveCodeBenchAdapterTests(unittest.TestCase):
    def test_exposes_adapter_metadata(self) -> None:
        adapter = benchmark_adapter("livecodebench")

        self.assertEqual(adapter.kind, "livecodebench")
        self.assertEqual(adapter.display_name, "LiveCodeBench")
        self.assertEqual(adapter.supported_harnesses, ("docker",))
        self.assertFalse(adapter.native_rollout)
        self.assertEqual(adapter.grading_schema, "yacht.livecodebench-grading.v1")

    def test_prompt_instructions_require_json_code_response(self) -> None:
        task = Task(
            id="abc301_a",
            title="lcb instance",
            difficulty=1,
            problem_statement="Overall Winner\n\nDetails here.",
        )

        instructions = benchmark_adapter("livecodebench").task_prompt_instructions(task)

        self.assertIn("LiveCodeBench submission instructions", instructions)
        self.assertIn("non-empty code string", instructions)
        self.assertIn("Overall Winner", instructions)

    def test_builds_launcher_command_with_window(self) -> None:
        command = benchmark_adapter("livecodebench").launcher_command(
            course_adapter={
                "kind": "livecodebench",
                "dataset": "livecodebench/code_generation_lite",
                "split": "release_v1",
                "harness": "docker",
                "start_date": "2023-05-01",
                "end_date": "2023-05-14",
            },
            tasks=[{"id": "abc301_a"}],
            candidate_path=Path("/tmp/vessels/v1/candidate-patches.jsonl"),
            native_report_dir=Path("/tmp/native-report"),
            run_id="run-1",
            vessel_name="v1",
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
                "yacht.courses.livecodebench.harness",
                "--candidates",
                "/tmp/vessels/v1/candidate-patches.jsonl",
                "--window-file",
                "/tmp/vessels/v1/lcb-window.json",
                "--work-dir",
                "/tmp/vessels/v1/lcb-eval",
                "--report-dir",
                "/tmp/native-report",
                "--run-id",
                "run-1",
                "--vessel",
                "v1",
                "--release-version",
                "release_v1",
                "--start-date",
                "2023-05-01",
                "--end-date",
                "2023-05-14",
            ],
        )


if __name__ == "__main__":
    unittest.main()


class LiveCodeBenchPipelineArtifactTests(unittest.TestCase):
    def test_plan_and_launcher_handoff_preserve_the_window(self) -> None:
        from yacht.courses.handoff import write_course_handoff
        from yacht.workflows.benchmark_execution_plan import (
            write_benchmark_execution_plan,
        )
        from yacht.workflows.benchmark_launcher_handoff import (
            write_benchmark_launcher_handoff,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(LIVECODEBENCH_CONFIG, encoding="utf-8")
            logbook_dir = root / "logbook"
            write_course_handoff(config_path, logbook_dir)

            plan = write_benchmark_execution_plan(logbook_dir)
            launcher = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)
            from yacht.workflows.benchmark_launch import (
                write_benchmark_launch_result,
            )
            from yacht.workflows.benchmark_grading_collection import (
                collect_benchmark_grading_reports,
            )
            from yacht.preflight import CommandResult

            launch = write_benchmark_launch_result(
                logbook_dir=logbook_dir,
                command_runner=lambda argv, cwd: CommandResult(
                    exit_code=0, stdout="", stderr=""
                ),
            )
            collection = collect_benchmark_grading_reports(
                config_path=config_path,
                logbook_dir=logbook_dir,
            )

            for document in (plan, launcher, launch, collection):
                self.assertEqual(document["adapter"]["kind"], "livecodebench")
                self.assertEqual(document["adapter"]["start_date"], "2023-05-01")
                self.assertEqual(document["adapter"]["end_date"], "2023-05-14")
