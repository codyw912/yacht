import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main


class RealSmokeRunbookTests(unittest.TestCase):
    def test_real_smoke_runbook_prints_commands_and_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-smoke-runbook",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            runbook = json.loads(stdout.getvalue())
            self.assertEqual(runbook["schema"], "yacht.real-smoke-runbook.v1")
            self.assertEqual(runbook["regatta"], "pi-fff-comparison")
            self.assertEqual(runbook["course"], "swe-bench-lite")
            self.assertEqual(runbook["agent"], "pi")
            self.assertEqual(
                runbook["secret_placeholders"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "argument": '--secret anthropic="$ANTHROPIC_API_KEY"',
                    }
                ],
            )

            commands = {step["name"]: step["command"] for step in runbook["steps"]}
            self.assertEqual(
                commands["real-smoke-eval"],
                (
                    f"uv run yacht real-smoke-eval {config_path} "
                    f"--logbook {logbook_dir} --workspace {workspace_path} "
                    '--secret anthropic="$ANTHROPIC_API_KEY"'
                ),
            )
            self.assertIn("--agent-preflight pi", commands["preflight"])
            self.assertIn("--agent pi", commands["task-attempts"])
            self.assertEqual(
                commands["smoke-readiness-report"],
                f"uv run yacht smoke-readiness-report --logbook {logbook_dir}",
            )

            artifacts = runbook["artifacts"]
            self.assertIn(
                str(
                    logbook_dir
                    / "preflight"
                    / "pi-vs-pi-fff"
                    / "pi-plus-fff.json"
                ),
                artifacts["preflight"],
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "task-attempts"
                    / "pi-vs-pi-fff"
                    / "pi-plus-fff"
                    / "django__django-11099.json"
                ),
                artifacts["task_attempts"],
            )
            self.assertEqual(
                artifacts["task_attempt_scorecard"],
                str(logbook_dir / "task-attempt-scorecard.json"),
            )
            self.assertEqual(
                artifacts["smoke_readiness_report"],
                str(logbook_dir / "smoke-readiness-report.json"),
            )
            self.assertEqual(
                artifacts["real_smoke_runbook"],
                str(logbook_dir / "real-smoke-runbook.json"),
            )
            self.assertEqual(
                json.loads(
                    (logbook_dir / "real-smoke-runbook.json").read_text(
                        encoding="utf-8"
                    )
                ),
                runbook,
            )

    def test_real_smoke_runbook_can_print_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-smoke-runbook",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--format",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            markdown = stdout.getvalue()
            self.assertIn("## Real Smoke Runbook", markdown)
            self.assertIn("Regatta: `pi-fff-comparison`", markdown)
            self.assertIn("### Commands", markdown)
            self.assertIn("```sh\nuv run yacht real-smoke-eval", markdown)
            self.assertIn('--secret anthropic="$ANTHROPIC_API_KEY"', markdown)
            self.assertIn("### Expected Artifacts", markdown)
            self.assertIn("logbook/smoke-readiness-report.json", markdown)

            runbook = json.loads(
                (logbook_dir / "real-smoke-runbook.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(runbook["schema"], "yacht.real-smoke-runbook.v1")
            self.assertEqual(runbook["regatta"], "pi-fff-comparison")


if __name__ == "__main__":
    unittest.main()
