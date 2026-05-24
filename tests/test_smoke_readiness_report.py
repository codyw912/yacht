import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.preflight_artifacts import write_preflight_artifact
from tests.test_provisioning import PI_FFF_TYPED_INSTALL, PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.harnesses.pi import PiTaskRequest, SubprocessPiTaskLauncher
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
            rigged = report["comparisons"][0]["vessels"][1]
            self.assertEqual(rigged["expected_tool_calls"], ["fffind"])
            self.assertEqual(rigged["missing_expected_tool_calls"], [])
            self.assertEqual(rigged["tool_call_counts"], {"fffind": 1})
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

    def test_smoke_readiness_report_blocks_missing_expected_tool_call(self) -> None:
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

            self._run_pi_smoke_eval(
                config_path,
                logbook_dir,
                workspace_path,
                tool_calls=("bash",),
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    ["smoke-readiness-report", "--logbook", str(logbook_dir)]
                )

            self.assertEqual(exit_code, 1)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["status"], "blocked")
            rigged = report["comparisons"][0]["vessels"][1]
            self.assertEqual(rigged["name"], "pi-plus-fff")
            self.assertEqual(rigged["status"], "missing-expected-tool-calls")
            self.assertEqual(rigged["expected_tool_calls"], ["fffind"])
            self.assertEqual(rigged["missing_expected_tool_calls"], ["fffind"])
            self.assertEqual(rigged["tool_call_counts"], {"bash": 1})
            self.assertEqual(rigged["reasons"], ["missing-expected-tool-calls"])

    def _write_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        config_path = root / "regatta.toml"
        workspace_path = root / "workspace"
        logbook_dir = root / "logbook"
        config_path.write_text(_config_without_install(), encoding="utf-8")
        workspace_path.mkdir()
        return config_path, workspace_path, logbook_dir

    def _run_pi_smoke_eval(
        self,
        config_path: Path,
        logbook_dir: Path,
        workspace_path: Path,
        tool_calls: tuple[str, ...] = ("fffind",),
    ) -> None:
        def runner(request: PiTaskRequest) -> CommandResult:
            tool_call_json = json.dumps(list(tool_calls))
            return CommandResult(
                exit_code=0,
                stdout=f'{{"completed": true, "tool_calls": {tool_call_json}}}\n',
                stderr="",
            )

        with patch(
            "yacht.harnesses.registry.SubprocessPiTaskLauncher",
            return_value=SubprocessPiTaskLauncher(runner=runner),
        ), patch(
            "yacht.courses.registry.SweBenchAdapter.task_with_context",
            autospec=True,
            side_effect=lambda self, *, task, adapter: task,
        ), patch(
            "yacht.courses.registry.SweBenchAdapter.workspace_for_attempt",
            autospec=True,
            return_value=workspace_path,
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


def _config_without_install() -> str:
    return PI_WITH_FFF_CONFIG.replace(
        PI_FFF_TYPED_INSTALL,
        "install = []\n",
    )


if __name__ == "__main__":
    unittest.main()
