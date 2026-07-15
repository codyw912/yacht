import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import create_fixture_repo, hermetic_swe_bench_config
from tests.test_provisioning import PI_FFF_TYPED_INSTALL, PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.harnesses.pi import (
    PiPromptRequest,
    PiTaskRequest,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
)
from yacht.logbook.index import RUN_INDEX_PATH
from yacht.preflight import CommandResult


class RealSmokeEvalTests(unittest.TestCase):
    def test_real_smoke_eval_uses_configured_local_smoke_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-smoke-eval",
                        "examples/local-agent-preflight-smoke.toml",
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "ready")
            self.assertEqual(summary["agent"], "local-smoke")
            self.assertEqual(summary["preflight"]["status"], "passed")
            self.assertEqual(summary["smoke_eval"]["status"], "complete")
            self.assertEqual(summary["smoke_eval"]["agent"], "local-smoke")
            self.assertEqual(summary["smoke_eval"]["attempts"]["attempt_count"], 2)
            self.assertEqual(summary["readiness"]["status"], "ready")
            run_index = json.loads(
                (logbook_dir / RUN_INDEX_PATH).read_text(encoding="utf-8")
            )
            self.assertEqual(run_index["schema"], "yacht.run-index.v1")
            self.assertEqual(run_index["run_kind"], "real-smoke")
            self.assertEqual(run_index["status"], "ready")
            self.assertEqual(
                run_index["config_path"],
                "examples/local-agent-preflight-smoke.toml",
            )
            self.assertEqual(run_index["logbook"], str(logbook_dir))
            self.assertEqual(run_index["regatta"], "local-agent-preflight-smoke")
            self.assertEqual(run_index["course"], "local-smoke")
            self.assertTrue(run_index["artifacts"]["smoke_readiness_report"]["present"])
            self.assertTrue((logbook_dir / "smoke-readiness-report.json").is_file())
            self.assertTrue((logbook_dir / "smoke-report.txt").is_file())

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
            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiPromptLauncher",
                    return_value=SubprocessPiPromptLauncher(runner=prompt_runner),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiTaskLauncher",
                    return_value=SubprocessPiTaskLauncher(runner=task_runner),
                ),
                redirect_stdout(stdout),
            ):
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
            self.assertEqual(
                summary["report_path"],
                str(logbook_dir / "smoke-report.txt"),
            )
            self.assertEqual(
                summary["artifacts"],
                {
                    "logbook": str(logbook_dir),
                    "smoke_report": str(logbook_dir / "smoke-report.txt"),
                    "smoke_readiness_report": str(
                        logbook_dir / "smoke-readiness-report.json"
                    ),
                    "task_attempt_scorecard": str(
                        logbook_dir / "task-attempt-scorecard.json"
                    ),
                },
            )
            self.assertIn(
                "pi-container-fff | ready | passed | measured | fffind:1",
                (logbook_dir / "smoke-report.txt").read_text(encoding="utf-8"),
            )

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
            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiPromptLauncher",
                    return_value=SubprocessPiPromptLauncher(runner=prompt_runner),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiTaskLauncher",
                    return_value=SubprocessPiTaskLauncher(runner=task_runner),
                ),
                redirect_stdout(stdout),
            ):
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
            self.assertTrue((logbook_dir / "smoke-report.txt").is_file())

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
            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(
                        exit_code=1,
                        stdout="",
                        stderr="pi unavailable",
                    ),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiPromptLauncher",
                    return_value=SubprocessPiPromptLauncher(
                        runner=_passing_prompt_runner
                    ),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiTaskLauncher",
                    return_value=SubprocessPiTaskLauncher(runner=task_runner),
                ),
                redirect_stdout(stdout),
            ):
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
                ["task-attempts", "smoke-readiness-report", "smoke-report"],
            )
            self.assertEqual(
                summary["artifacts"],
                {
                    "logbook": str(logbook_dir),
                    "smoke_report": str(logbook_dir / "smoke-report.txt"),
                    "smoke_readiness_report": str(
                        logbook_dir / "smoke-readiness-report.json"
                    ),
                    "task_attempt_scorecard": str(
                        logbook_dir / "task-attempt-scorecard.json"
                    ),
                },
            )
            self.assertEqual(task_requests, [])
            self.assertFalse((logbook_dir / "task-attempts").exists())
            self.assertFalse((logbook_dir / "smoke-readiness-report.json").exists())
            self.assertFalse((logbook_dir / "smoke-report.txt").exists())

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
            self.assertFalse((logbook_dir / "smoke-report.txt").exists())


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    logbook_dir = root / "logbook"
    repo = create_fixture_repo(root / "repo")
    config_path.write_text(
        hermetic_swe_bench_config(_config_without_install(), repo),
        encoding="utf-8",
    )
    workspace_path.mkdir()
    return config_path, workspace_path, logbook_dir


def _config_without_install() -> str:
    return PI_WITH_FFF_CONFIG.replace(
        PI_FFF_TYPED_INSTALL,
        "install = []\n",
    )


def _container_pi_fff_real_smoke_config_without_install() -> str:
    return (
        Path("examples/container-pi-fff-real-task-smoke.toml")
        .read_text(
            encoding="utf-8",
        )
        .replace(
            PI_FFF_TYPED_INSTALL,
            "install = []\n",
        )
    )


def _passing_prompt_runner(request: PiPromptRequest) -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout='{"available": true, "configured": true, "tool_calls": ["fffind"]}\n',
        stderr="",
    )


if __name__ == "__main__":
    unittest.main()
