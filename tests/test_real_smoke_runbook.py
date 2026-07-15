import json
import tempfile
import unittest
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.workflows.real_smoke_runbook import (
    render_real_smoke_runbook,
    write_real_smoke_runbook,
)


class RealSmokeRunbookTests(unittest.TestCase):
    def test_real_smoke_runbook_uses_configured_local_smoke_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            workspace_path.mkdir()

            runbook = write_real_smoke_runbook(
                config_path=Path("examples/local-agent-preflight-smoke.toml"),
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
            )
            self.assertEqual(runbook["agent"], "local-smoke")
            commands = {step["name"]: step["command"] for step in runbook["steps"]}
            self.assertIn("--agent-preflight local-smoke", commands["preflight"])
            self.assertIn("--agent local-smoke", commands["task-attempts"])
            self.assertNotIn("pi-smoke-eval", commands)

    def test_real_smoke_runbook_prints_commands_and_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            runbook = write_real_smoke_runbook(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
            )

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
                commands["run"],
                (
                    f"uv run yacht run {config_path} "
                    f"--logbook {logbook_dir} --workspace {workspace_path} "
                    '--secret anthropic="$ANTHROPIC_API_KEY"'
                ),
            )
            self.assertIn("--agent-preflight pi", commands["preflight"])
            self.assertIn("uv run yacht internals preflight", commands["preflight"])
            self.assertIn("--agent pi", commands["task-attempts"])
            self.assertIn(
                "uv run yacht internals task-attempts",
                commands["task-attempts"],
            )
            self.assertEqual(
                commands["smoke-readiness-report"],
                (
                    "uv run yacht internals smoke-readiness-report "
                    f"--logbook {logbook_dir}"
                ),
            )
            self.assertEqual(
                commands["report"],
                f"uv run yacht report --logbook {logbook_dir}",
            )

            artifacts = runbook["artifacts"]
            self.assertIn(
                str(logbook_dir / "preflight" / "pi-vs-pi-fff" / "pi-plus-fff.json"),
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
                artifacts["smoke_report"],
                str(logbook_dir / "smoke-report.txt"),
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

            markdown = render_real_smoke_runbook(
                write_real_smoke_runbook(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                )
            )
            self.assertIn("## Real Smoke Runbook", markdown)
            self.assertIn("Regatta: `pi-fff-comparison`", markdown)
            self.assertIn("### Commands", markdown)
            self.assertIn("```sh\nuv run yacht run", markdown)
            self.assertIn('--secret anthropic="$ANTHROPIC_API_KEY"', markdown)
            self.assertIn("### Expected Artifacts", markdown)
            self.assertIn("logbook/smoke-readiness-report.json", markdown)
            self.assertIn("logbook/smoke-report.txt", markdown)

            runbook = json.loads(
                (logbook_dir / "real-smoke-runbook.json").read_text(encoding="utf-8")
            )
            self.assertEqual(runbook["schema"], "yacht.real-smoke-runbook.v1")
            self.assertEqual(runbook["regatta"], "pi-fff-comparison")


if __name__ == "__main__":
    unittest.main()
