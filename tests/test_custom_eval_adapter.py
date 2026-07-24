import tempfile
import unittest
from pathlib import Path

from yacht.courses.handoff import write_course_handoff
from yacht.courses.task_directory import task_directory_digest
from yacht.courses.terminal_bench.harness import (
    harbor_command,
    harbor_run_config,
    run_terminal_bench_job,
)
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import ConfigError, load_regatta


CUSTOM_EVAL_CONFIG = """
[regatta]
name = "custom-eval-comparison"

[preflight]
failure_policy = "abort-group"

[course]
name = "team-evals"

[[course.tasks]]
id = "hello-task"
title = "Greet the user from a container"

[course.adapter]
kind = "custom-eval"
dataset = "evals"
split = "v1"
harness = "harbor"

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.harbor-claude]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "claude-code"
harness_version = "2.1.211"
required_secrets = ["anthropic"]

[[vessels]]
name = "claude-baseline"
model = "claude-haiku-4-5"
runtime = "harbor-claude"

[[vessels]]
name = "claude-candidate"
model = "claude-haiku-4-5"
runtime = "harbor-claude"

[[comparisons]]
name = "baseline-vs-candidate"
course = "team-evals"
vessels = ["claude-baseline", "claude-candidate"]
"""


def _write_task_directory(root: Path) -> Path:
    tasks_dir = root / "evals"
    task_dir = tasks_dir / "hello-task"
    task_dir.mkdir(parents=True)
    (task_dir / "instruction.md").write_text("Print a greeting.\n", encoding="utf-8")
    (task_dir / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
    return tasks_dir


def _write_config(root: Path) -> Path:
    config_path = root / "regatta.toml"
    config_path.write_text(CUSTOM_EVAL_CONFIG, encoding="utf-8")
    return config_path


class TaskDirectoryDigestTests(unittest.TestCase):
    def test_digest_is_stable_for_identical_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_dir = _write_task_directory(Path(temp_dir))

            first = task_directory_digest(tasks_dir)
            second = task_directory_digest(tasks_dir)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("sha256:"))

    def test_digest_changes_when_file_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_dir = _write_task_directory(Path(temp_dir))
            before = task_directory_digest(tasks_dir)

            (tasks_dir / "hello-task" / "instruction.md").write_text(
                "Print a different greeting.\n", encoding="utf-8"
            )

            self.assertNotEqual(before, task_directory_digest(tasks_dir))

    def test_digest_changes_when_a_file_is_renamed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_dir = _write_task_directory(Path(temp_dir))
            before = task_directory_digest(tasks_dir)

            source = tasks_dir / "hello-task" / "instruction.md"
            source.rename(tasks_dir / "hello-task" / "task.md")

            self.assertNotEqual(before, task_directory_digest(tasks_dir))

    def test_rejects_a_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ConfigError, "not found"):
                task_directory_digest(Path(temp_dir) / "missing")

    def test_rejects_an_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir) / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(ConfigError, "empty"):
                task_directory_digest(empty)


class CustomEvalConfigTests(unittest.TestCase):
    def test_resolves_relative_dataset_path_against_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_task_directory(root)
            config_path = _write_config(root)

            regatta = load_regatta(config_path)

        adapter = regatta.course.adapter
        assert adapter is not None
        self.assertEqual(adapter.dataset, str((root / "evals").resolve()))
        self.assertEqual(adapter.split, "v1")

    def test_keeps_absolute_dataset_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            config_path = root / "regatta.toml"
            config_path.write_text(
                CUSTOM_EVAL_CONFIG.replace(
                    'dataset = "evals"', f'dataset = "{tasks_dir}"'
                ),
                encoding="utf-8",
            )

            regatta = load_regatta(config_path)

        adapter = regatta.course.adapter
        assert adapter is not None
        self.assertEqual(adapter.dataset, str(tasks_dir.resolve()))

    def test_rejects_non_harbor_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_task_directory(root)
            config_path = root / "regatta.toml"
            config_path.write_text(
                CUSTOM_EVAL_CONFIG.replace(
                    'harness = "harbor"', 'harness = "docker"', 1
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError, "course.adapter.harness must be one of: harbor"
            ):
                load_regatta(config_path)


class CustomEvalHandoffTests(unittest.TestCase):
    def test_handoff_records_the_task_directory_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"

            handoff = write_course_handoff(config_path, logbook_dir)

            adapter = handoff["adapter"]
            self.assertEqual(adapter["kind"], "custom-eval")
            self.assertEqual(adapter["dataset"], str(tasks_dir.resolve()))
            self.assertEqual(
                adapter["content_digest"], task_directory_digest(tasks_dir)
            )

    def test_handoff_fails_when_the_task_directory_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"

            with self.assertRaisesRegex(ConfigError, "not found"):
                write_course_handoff(config_path, logbook_dir)


class CustomEvalJobTests(unittest.TestCase):
    def test_job_dataset_carries_the_path_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            config_path = _write_config(root)
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(
                regatta=regatta, vessel_name="claude-baseline"
            )

            self.assertEqual(
                job["dataset"],
                {
                    "path": str(tasks_dir.resolve()),
                    "digest": task_directory_digest(tasks_dir),
                },
            )
            self.assertEqual(job["tasks"], ["hello-task"])


class CustomEvalHarnessTests(unittest.TestCase):
    def _job(self, tasks_dir: Path) -> dict:
        return {
            "schema": "yacht.terminal-bench-job.v1",
            "dataset": {
                "path": str(tasks_dir),
                "digest": task_directory_digest(tasks_dir),
            },
            "tasks": ["hello-task"],
            "agent": {
                "name": "claude-code",
                "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
                "env": {},
                "mcp_servers": [],
                "rigging_steps": [],
            },
            "launcher_image": "yacht/harbor-launcher:harbor-0.20.0",
            "secret_env": ["ANTHROPIC_API_KEY"],
            "vessel": "claude-baseline",
        }

    def test_harbor_run_config_uses_the_path_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)

            config = harbor_run_config(self._job(tasks_dir), trials_dir=root / "trials")

            self.assertEqual(
                config["datasets"],
                [{"path": str(tasks_dir), "task_names": ["hello-task"]}],
            )

    def test_harbor_command_mounts_the_task_directory_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            trials_dir = root / "trials"

            command = harbor_command(
                trials_dir / "harbor-run-config.json",
                trials_dir=trials_dir,
                secret_env=["ANTHROPIC_API_KEY"],
                tasks_path=tasks_dir,
            )

            self.assertIn(f"{tasks_dir}:{tasks_dir}:ro", command)

    def test_run_rejects_a_changed_task_directory(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            job = self._job(tasks_dir)
            job_path = root / "job.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            roster_path = root / "roster.jsonl"
            roster_path.write_text(
                json.dumps({"instance_id": "hello-task"}) + "\n",
                encoding="utf-8",
            )

            (tasks_dir / "hello-task" / "instruction.md").write_text(
                "Changed after planning.\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ConfigError, "content digest"):
                run_terminal_bench_job(
                    job_path=job_path,
                    roster_path=roster_path,
                    trials_dir=root / "trials",
                    report_dir=root / "report",
                    run_id="run-1",
                    vessel_name="claude-baseline",
                    command_runner=lambda argv, cwd: 0,
                )

    def test_run_rejects_a_path_dataset_without_a_digest(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            job = self._job(tasks_dir)
            del job["dataset"]["digest"]
            job_path = root / "job.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            roster_path = root / "roster.jsonl"
            roster_path.write_text(
                json.dumps({"instance_id": "hello-task"}) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "content digest"):
                run_terminal_bench_job(
                    job_path=job_path,
                    roster_path=roster_path,
                    trials_dir=root / "trials",
                    report_dir=root / "report",
                    run_id="run-1",
                    vessel_name="claude-baseline",
                    command_runner=lambda argv, cwd: 0,
                )


class CustomEvalPipelineArtifactTests(unittest.TestCase):
    def test_pipeline_artifacts_preserve_the_content_digest(self) -> None:
        from yacht.preflight import CommandResult
        from yacht.workflows.benchmark_execution_plan import (
            write_benchmark_execution_plan,
        )
        from yacht.workflows.benchmark_grading_collection import (
            collect_benchmark_grading_reports,
        )
        from yacht.workflows.benchmark_launch import write_benchmark_launch_result
        from yacht.workflows.benchmark_launcher_handoff import (
            write_benchmark_launcher_handoff,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_dir = _write_task_directory(root)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            digest = task_directory_digest(tasks_dir)

            write_course_handoff(config_path, logbook_dir)
            plan = write_benchmark_execution_plan(logbook_dir)
            launcher = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)
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
                self.assertEqual(document["adapter"]["kind"], "custom-eval")
                self.assertEqual(document["adapter"]["content_digest"], digest)


if __name__ == "__main__":
    unittest.main()
