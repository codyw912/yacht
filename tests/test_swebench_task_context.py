import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from yacht.regatta import CourseAdapter, Metrics, Task, load_regatta
from yacht.swebench_task_context import (
    materialize_swe_bench_workspace,
    task_with_swe_bench_context,
)
from yacht.task_attempt_runner import run_task_attempts
from yacht.task_attempts import AgentTaskResult


class SweBenchTaskContextTests(unittest.TestCase):
    def test_loads_swe_bench_task_context_from_dataset(self) -> None:
        def load_dataset(dataset: str, *, split: str):
            self.assertEqual(dataset, "SWE-bench/SWE-bench_Lite")
            self.assertEqual(split, "test")
            return [
                {
                    "instance_id": "django__django-11099",
                    "repo": "django/django",
                    "base_commit": "abc123",
                    "problem_statement": "Fix the Django regression.",
                }
            ]

        fake_datasets = SimpleNamespace(load_dataset=load_dataset)
        with patch.dict("sys.modules", {"datasets": fake_datasets}):
            task = task_with_swe_bench_context(
                task=Task(
                    id="django__django-11099",
                    title="Django regression",
                    difficulty=1,
                ),
                adapter=CourseAdapter(
                    kind="swe-bench",
                    dataset="princeton-nlp/SWE-bench_Lite",
                    split="test",
                    harness="docker",
                ),
            )

        self.assertEqual(task.repo, "django/django")
        self.assertEqual(task.repo_url, "https://github.com/django/django.git")
        self.assertEqual(task.base_commit, "abc123")
        self.assertEqual(task.problem_statement, "Fix the Django regression.")

    def test_loads_inline_swe_bench_task_context_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = _create_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(_config(repo), encoding="utf-8")

            regatta = load_regatta(config_path)
            task = regatta.course.tasks[0]

            self.assertEqual(task.repo, "example/repo")
            self.assertEqual(task.repo_url, str(repo))
            self.assertEqual(task.base_commit, _base_commit(repo))
            self.assertEqual(task.problem_statement, "Fix the regression.")

    def test_materializes_swe_bench_workspace_at_base_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = _create_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(_config(repo), encoding="utf-8")
            task = load_regatta(config_path).course.tasks[0]

            workspace = materialize_swe_bench_workspace(
                task=task,
                workspace_root=root / "workspaces",
                comparison_name="comparison",
                vessel_name="vessel",
            )

            self.assertEqual((workspace / "example.txt").read_text(), "base\n")
            self.assertEqual(_head(workspace), task.base_commit)

    def test_swe_bench_task_attempt_runs_in_materialized_task_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = _create_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(_config(repo, with_runtime=True), encoding="utf-8")
            calls = []

            class RecordingAgent:
                def run_task(
                    self,
                    *,
                    instance,
                    task,
                    prompt,
                    env,
                    cwd,
                    transcript_path,
                ):
                    calls.append((task, prompt, cwd, instance.workspace_path))
                    return AgentTaskResult(
                        exit_code=0,
                        response='{"model_patch": "diff --git a/example.txt b/example.txt\\n--- a/example.txt\\n+++ b/example.txt\\n"}',
                        tool_calls=(),
                        transcript_path=transcript_path,
                        metrics=Metrics(tokens=1, duration_seconds=0.0),
                    )

            run_task_attempts(
                config_path=config_path,
                logbook_dir=root / "logbook",
                workspace_path=root / "yacht-workspace",
                secret_values={},
                agent_name="pi",
                task_agent=RecordingAgent(),
            )

            task, prompt, cwd, instance_workspace = calls[0]
            self.assertEqual(task.problem_statement, "Fix the regression.")
            self.assertIn("Problem statement:\nFix the regression.", prompt)
            self.assertEqual(cwd, instance_workspace)
            self.assertEqual((cwd / "example.txt").read_text(), "base\n")


def _create_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "example.txt").write_text("base\n", encoding="utf-8")
    _git(path, "add", "example.txt")
    _git(path, "commit", "-m", "base")
    (path / "example.txt").write_text("later\n", encoding="utf-8")
    _git(path, "commit", "-am", "later")
    return path


def _head(path: Path) -> str:
    return _git(path, "rev-parse", "HEAD")


def _base_commit(path: Path) -> str:
    return _git(path, "rev-list", "--max-parents=0", "HEAD")


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=path,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _config(repo: Path, *, with_runtime: bool = False) -> str:
    base_commit = _base_commit(repo)
    runtime = """
[runtimes.pi]
backend = "host-nix"
flake = "path:.#pi"
command = ["pi"]
""" if with_runtime else ""
    vessel_runtime = 'runtime = "pi"' if with_runtime else ""
    return f"""
[regatta]
name = "swe-bench-context-smoke"

[course]
name = "swe-bench-lite"
tasks = [
  {{ id = "example__repo-1", title = "Fix regression", difficulty = 1, repo = "example/repo", repo_url = "{repo}", base_commit = "{base_commit}", problem_statement = "Fix the regression." }},
]

[course.adapter]
kind = "swe-bench"
dataset = "SWE-bench/SWE-bench_Lite"
split = "test"
harness = "docker"

{runtime}

[[vessels]]
name = "baseline"
model = "mock"
{vessel_runtime}

[[vessels]]
name = "challenger"
model = "mock"
{vessel_runtime}

[[comparisons]]
name = "comparison"
course = "swe-bench-lite"
vessels = ["baseline", "challenger"]
"""


if __name__ == "__main__":
    unittest.main()
