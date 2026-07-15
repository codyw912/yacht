import json
import tempfile
import unittest
from contextlib import redirect_stdout
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import create_fixture_repo, hermetic_swe_bench_config
from tests.test_provisioning import PI_FFF_TYPED_INSTALL, PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.harnesses.pi import PiTaskRequest, SubprocessPiTaskLauncher
from yacht.preflight import CommandResult


class CliPiTaskAttemptTests(unittest.TestCase):
    def test_task_attempts_command_can_run_pi_with_patched_subprocess_launcher(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            requests = []
            repo = create_fixture_repo(root / "repo")
            config_path.write_text(
                _hermetic_config(_config_without_install(), repo),
                encoding="utf-8",
            )
            workspace_path.mkdir()

            def runner(request: PiTaskRequest) -> CommandResult:
                requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout='{"completed": true, "tool_calls": ["fff"]}\n',
                    stderr="",
                )

            stdout = StringIO()
            with (
                patch(
                    "yacht.harnesses.registry.SubprocessPiTaskLauncher",
                    return_value=SubprocessPiTaskLauncher(runner=runner),
                ),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "internals",
                        "task-attempts",
                        str(config_path),
                        "--agent",
                        "pi",
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
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["agent"], "pi")
            self.assertEqual(summary["attempt_count"], 2)
            self.assertEqual(len(requests), 2)
            baseline_request = requests[0]
            rigged_request = requests[1]
            self.assertNotIn("Rigging instructions:", baseline_request.prompt)
            self.assertIn("Rigging instructions:", rigged_request.prompt)
            self.assertIn(
                "Use fff for codebase memory and navigation.",
                rigged_request.prompt,
            )

            attempt_path = (
                logbook_dir
                / "task-attempts"
                / "pi-vs-pi-fff"
                / "pi-plus-fff"
                / "django__django-11099.json"
            )
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            self.assertEqual(attempt["agent"]["tool_calls"], ["fff"])
            self.assertNotIn("test-secret", json.dumps(attempt))

    def test_task_attempts_command_reports_missing_pi_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            repo = create_fixture_repo(root / "repo")
            config_path.write_text(
                _hermetic_config(_config_without_install(), repo),
                encoding="utf-8",
            )
            workspace_path.mkdir()

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "internals",
                        "task-attempts",
                        str(config_path),
                        "--agent",
                        "pi",
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
            self.assertFalse((logbook_dir / "task-attempts").exists())
            self.assertFalse((logbook_dir / "swe-bench-workspaces").exists())


def _config_without_install() -> str:
    return PI_WITH_FFF_CONFIG.replace(
        PI_FFF_TYPED_INSTALL,
        "install = []\n",
    )


def _hermetic_config(config: str, repo: Path) -> str:
    return hermetic_swe_bench_config(config, repo)


if __name__ == "__main__":
    unittest.main()
