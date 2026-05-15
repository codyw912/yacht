import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.pi_adapter import (
    PiPromptRequest,
    PiTaskRequest,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
)
from yacht.preflight import CommandResult


class RealSmokeEvalTests(unittest.TestCase):
    def test_real_smoke_eval_runs_container_pi_fff_example_to_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "container-pi-fff-real-task-smoke.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(
                _container_pi_fff_real_smoke_config_without_install(),
                encoding="utf-8",
            )
            workspace_path.mkdir()
            prompt_requests = []
            task_requests = []

            def prompt_runner(request: PiPromptRequest) -> CommandResult:
                prompt_requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout=(
                        '{"available": true, "configured": true, '
                        '"tool_calls": ["fffind"]}\n'
                    ),
                    stderr="",
                )

            def task_runner(request: PiTaskRequest) -> CommandResult:
                task_requests.append(request)
                if "Rigging instructions:" in request.prompt:
                    tool_calls = ["fffind"]
                else:
                    tool_calls = []
                return CommandResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {"completed": True, "tool_calls": tool_calls},
                    ),
                    stderr="",
                )

            stdout = StringIO()
            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), patch(
                "yacht.cli.SubprocessPiPromptLauncher",
                return_value=SubprocessPiPromptLauncher(runner=prompt_runner),
            ), patch(
                "yacht.cli.SubprocessPiTaskLauncher",
                return_value=SubprocessPiTaskLauncher(runner=task_runner),
            ), redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-smoke-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--secret",
                        "anthropic=test-secret",
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "ready")
            self.assertEqual(summary["preflight"]["status"], "passed")
            self.assertEqual(summary["smoke_eval"]["status"], "complete")
            self.assertEqual(summary["readiness"]["status"], "ready")
            self.assertEqual(len(prompt_requests), 1)
            self.assertEqual(len(task_requests), 2)
            rigged = summary["readiness"]["comparisons"][0]["vessels"][1]
            self.assertEqual(rigged["name"], "pi-container-fff")
            self.assertEqual(rigged["expected_tool_calls"], ["fffind"])
            self.assertEqual(rigged["missing_expected_tool_calls"], [])
            self.assertEqual(rigged["tool_call_counts"], {"fffind": 1})

    def test_real_smoke_eval_runs_preflight_attempts_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = _write_fixture(Path(temp_dir))
            prompt_requests = []
            task_requests = []

            def prompt_runner(request: PiPromptRequest) -> CommandResult:
                prompt_requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout=(
                        '{"available": true, "configured": true, '
                        '"tool_calls": ["fffind"]}\n'
                    ),
                    stderr="",
                )

            def task_runner(request: PiTaskRequest) -> CommandResult:
                task_requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout='{"completed": true, "tool_calls": ["fffind"]}\n',
                    stderr="",
                )

            stdout = StringIO()
            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), patch(
                "yacht.cli.SubprocessPiPromptLauncher",
                return_value=SubprocessPiPromptLauncher(runner=prompt_runner),
            ), patch(
                "yacht.cli.SubprocessPiTaskLauncher",
                return_value=SubprocessPiTaskLauncher(runner=task_runner),
            ), redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-smoke-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--secret",
                        "anthropic=test-secret",
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "ready")
            self.assertEqual(summary["agent"], "pi")
            self.assertEqual(summary["preflight"]["status"], "passed")
            self.assertEqual(summary["smoke_eval"]["status"], "complete")
            self.assertEqual(summary["smoke_eval"]["attempts"]["attempt_count"], 2)
            self.assertEqual(summary["readiness"]["status"], "ready")
            self.assertEqual(
                summary["readiness"]["summary"]["passed_agent_prompt_checks"],
                1,
            )
            self.assertEqual(len(prompt_requests), 1)
            self.assertEqual(len(task_requests), 2)
            self.assertTrue((logbook_dir / "smoke-readiness-report.json").is_file())

    def test_real_smoke_eval_stops_before_task_attempts_when_preflight_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = _write_fixture(Path(temp_dir))
            task_requests = []

            def task_runner(request: PiTaskRequest) -> CommandResult:
                task_requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout='{"completed": true, "tool_calls": ["fffind"]}\n',
                    stderr="",
                )

            stdout = StringIO()
            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(
                    exit_code=1,
                    stdout="",
                    stderr="pi unavailable",
                ),
            ), patch(
                "yacht.cli.SubprocessPiPromptLauncher",
                return_value=SubprocessPiPromptLauncher(
                    runner=_passing_prompt_runner
                ),
            ), patch(
                "yacht.cli.SubprocessPiTaskLauncher",
                return_value=SubprocessPiTaskLauncher(runner=task_runner),
            ), redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-smoke-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--secret",
                        "anthropic=test-secret",
                    ]
                )

            self.assertEqual(exit_code, 1)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["preflight"]["status"], "invalid")
            self.assertEqual(
                summary["skipped"],
                ["pi-smoke-eval", "smoke-readiness-report"],
            )
            self.assertEqual(task_requests, [])
            self.assertFalse((logbook_dir / "task-attempts").exists())
            self.assertFalse((logbook_dir / "smoke-readiness-report.json").exists())

    def test_real_smoke_eval_reports_missing_secret_without_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = _write_fixture(Path(temp_dir))

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "real-smoke-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "missing value for required secret anthropic",
                stderr.getvalue(),
            )
            self.assertFalse((logbook_dir / "preflight").exists())
            self.assertFalse((logbook_dir / "task-attempts").exists())
            self.assertFalse((logbook_dir / "smoke-readiness-report.json").exists())


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    logbook_dir = root / "logbook"
    config_path.write_text(_config_without_install(), encoding="utf-8")
    workspace_path.mkdir()
    return config_path, workspace_path, logbook_dir


def _config_without_install() -> str:
    return PI_WITH_FFF_CONFIG.replace(
        'install = ["npm:@ff-labs/pi-fff"]',
        "install = []",
    )


def _container_pi_fff_real_smoke_config_without_install() -> str:
    return Path("examples/container-pi-fff-real-task-smoke.toml").read_text(
        encoding="utf-8",
    ).replace(
        'install = ["npm:@ff-labs/pi-fff"]',
        "install = []",
    )


def _passing_prompt_runner(request: PiPromptRequest) -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout='{"available": true, "configured": true, "tool_calls": ["fffind"]}\n',
        stderr="",
    )


if __name__ == "__main__":
    unittest.main()
