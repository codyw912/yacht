import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import (
    REGATTA_CONFIG,
    create_fixture_repo,
    hermetic_swe_bench_config,
)
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main

SMOKE_CONFIG = """
[regatta]
name = "run-smoke"

[course]
name = "local-smoke"
tasks = [
  { id = "task-1", title = "Answer a prompt", difficulty = 1 },
]

[runtimes.local]
backend = "host-nix"
harness = "local"
flake = "path:.#local"
command = ["local-agent"]

[[vessels]]
name = "baseline"
model = "mock"
runtime = "local"

[[vessels]]
name = "challenger"
model = "mock"
runtime = "local"

[[comparisons]]
name = "baseline-vs-challenger"
course = "local-smoke"
vessels = ["baseline", "challenger"]
"""


class UnifiedRunCommandTests(unittest.TestCase):
    def test_mock_course_runs_end_to_end_without_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    ["run", str(config_path), "--logbook", str(root / "logbook")]
                )

            self.assertEqual(exit_code, 0)
            scorecard = json.loads(stdout.getvalue())
            self.assertEqual(scorecard["regatta"], "memory-smoke-test")
            self.assertTrue((root / "logbook" / "scorecard.json").is_file())

    def test_smoke_course_routes_to_real_smoke_eval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(SMOKE_CONFIG, encoding="utf-8")

            exit_code, mocks, stdout = self._run_patched(
                ["run", str(config_path), "--logbook", str(root / "logbook")],
                {
                    "run_real_smoke_eval": {"status": "ready"},
                    "write_real_smoke_runbook": {},
                    "configured_harness_name": "local",
                    "agent_prompt_runner_factory": None,
                    "task_agent": None,
                },
            )

            self.assertEqual(exit_code, 0)
            mocks["write_real_smoke_runbook"].assert_called_once()
            mocks["run_real_smoke_eval"].assert_called_once()
            self.assertEqual(
                mocks["run_real_smoke_eval"].call_args.kwargs["agent_name"],
                "local",
            )
            self.assertEqual(json.loads(stdout)["status"], "ready")

    def test_benchmark_course_routes_to_real_benchmark_eval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = create_fixture_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(
                hermetic_swe_bench_config(PI_WITH_FFF_CONFIG, repo),
                encoding="utf-8",
            )

            exit_code, mocks, stdout = self._run_patched(
                [
                    "run",
                    str(config_path),
                    "--logbook",
                    str(root / "logbook"),
                    "--format",
                    "json",
                ],
                {
                    "run_real_benchmark_eval": {"status": "complete"},
                    "write_real_benchmark_runbook": {},
                    "configured_harness_name": "pi",
                    "agent_prompt_runner_factory": None,
                    "task_agent": None,
                },
            )

            self.assertEqual(exit_code, 0)
            mocks["write_real_benchmark_runbook"].assert_called_once()
            mocks["run_real_benchmark_eval"].assert_called_once()
            self.assertEqual(json.loads(stdout)["status"], "complete")

    def test_benchmark_failure_status_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = create_fixture_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(
                hermetic_swe_bench_config(PI_WITH_FFF_CONFIG, repo),
                encoding="utf-8",
            )

            exit_code, _, _ = self._run_patched(
                [
                    "run",
                    str(config_path),
                    "--logbook",
                    str(root / "logbook"),
                    "--format",
                    "json",
                ],
                {
                    "run_real_benchmark_eval": {"status": "blocked"},
                    "write_real_benchmark_runbook": {},
                    "configured_harness_name": "pi",
                    "agent_prompt_runner_factory": None,
                    "task_agent": None,
                },
            )

            self.assertEqual(exit_code, 1)

    def test_repetitions_route_to_repeated_benchmark_eval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = create_fixture_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(
                hermetic_swe_bench_config(PI_WITH_FFF_CONFIG, repo),
                encoding="utf-8",
            )

            exit_code, mocks, _ = self._run_patched(
                [
                    "run",
                    str(config_path),
                    "--logbook",
                    str(root / "logbook"),
                    "--repetitions",
                    "3",
                    "--format",
                    "json",
                ],
                {
                    "run_real_benchmark_repetitions": {"status": "complete"},
                    "configured_harness_name": "pi",
                    "agent_prompt_runner_factory": None,
                    "task_agent": None,
                },
            )

            self.assertEqual(exit_code, 0)
            call = mocks["run_real_benchmark_repetitions"].call_args
            self.assertEqual(call.kwargs["repetitions"], 3)

    def test_repetitions_are_rejected_for_smoke_courses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(SMOKE_CONFIG, encoding="utf-8")
            stderr = StringIO()

            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "run",
                        str(config_path),
                        "--logbook",
                        str(root / "logbook"),
                        "--repetitions",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("--repetitions requires a course adapter", stderr.getvalue())

    def test_invalid_config_reports_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text("[regatta]\n", encoding="utf-8")
            stderr = StringIO()

            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = main(["run", str(config_path)])

            self.assertEqual(exit_code, 1)
            self.assertIn("error: invalid regatta config:", stderr.getvalue())

    def _run_patched(self, argv, patches):
        mocks = {}
        with ExitStack() as stack:
            for name, value in patches.items():
                mocks[name] = stack.enter_context(
                    patch(f"yacht.cli.commands.regatta.{name}", return_value=value)
                )
            stdout = StringIO()
            with redirect_stdout(stdout), redirect_stderr(StringIO()):
                exit_code = main(argv)
        return exit_code, mocks, stdout.getvalue()


if __name__ == "__main__":
    unittest.main()
