import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.preflight_artifacts import write_preflight_artifact
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.pi_adapter import PiTaskRequest, SubprocessPiTaskLauncher
from yacht.preflight import CommandResult


class SmokeReadinessReportTests(unittest.TestCase):
    def test_smoke_readiness_report_passes_with_preflight_attempts_and_scorecard(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = self._write_fixture(
                Path(temp_dir)
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="passed",
                include_agent_prompt=True,
            )

            self._run_pi_smoke_eval(config_path, logbook_dir, workspace_path)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    ["smoke-readiness-report", "--logbook", str(logbook_dir)]
                )

            self.assertEqual(exit_code, 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["schema"], "yacht.smoke-readiness-report.v1")
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["summary"]["ready_vessels"], 2)
            self.assertEqual(report["summary"]["passed_agent_prompt_checks"], 1)
            self.assertTrue((logbook_dir / "smoke-readiness-report.json").is_file())

    def test_smoke_readiness_report_blocks_without_agent_prompt_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = self._write_fixture(
                Path(temp_dir)
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="passed",
            )

            self._run_pi_smoke_eval(config_path, logbook_dir, workspace_path)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    ["smoke-readiness-report", "--logbook", str(logbook_dir)]
                )

            self.assertEqual(exit_code, 1)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["summary"]["ready_vessels"], 0)
            self.assertEqual(report["summary"]["blocked_vessels"], 2)
            self.assertEqual(report["summary"]["passed_agent_prompt_checks"], 0)
            self.assertEqual(
                report["comparisons"][0]["vessels"][0]["status"],
                "missing-agent-prompt-evidence",
            )

    def test_smoke_readiness_report_blocks_missing_preflight_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = self._write_fixture(
                Path(temp_dir)
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="passed",
                include_agent_prompt=True,
            )

            self._run_pi_smoke_eval(config_path, logbook_dir, workspace_path)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    ["smoke-readiness-report", "--logbook", str(logbook_dir)]
                )

            self.assertEqual(exit_code, 1)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["status"], "blocked")
            baseline = report["comparisons"][0]["vessels"][0]
            self.assertEqual(baseline["name"], "pi-baseline")
            self.assertEqual(baseline["status"], "missing-preflight")
            self.assertEqual(baseline["reasons"], ["missing-preflight"])

    def _write_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        config_path = root / "regatta.toml"
        workspace_path = root / "workspace"
        logbook_dir = root / "logbook"
        config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
        workspace_path.mkdir()
        return config_path, workspace_path, logbook_dir

    def _run_pi_smoke_eval(
        self,
        config_path: Path,
        logbook_dir: Path,
        workspace_path: Path,
    ) -> None:
        def runner(request: PiTaskRequest) -> CommandResult:
            return CommandResult(
                exit_code=0,
                stdout='{"completed": true, "tool_calls": ["fff"]}\n',
                stderr="",
            )

        with patch(
            "yacht.cli.SubprocessPiTaskLauncher",
            return_value=SubprocessPiTaskLauncher(runner=runner),
        ), redirect_stdout(StringIO()):
            self.assertEqual(
                main(
                    [
                        "pi-smoke-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--secret",
                        "anthropic=test-secret",
                    ]
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
