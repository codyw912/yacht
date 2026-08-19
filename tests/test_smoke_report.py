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
from yacht.reports.smoke_report import render_smoke_report


class SmokeReportTests(unittest.TestCase):
    def test_render_smoke_report_summarizes_readiness_and_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path, workspace_path, logbook_dir = _write_fixture(Path(temp_dir))
            _write_passed_preflights(logbook_dir)
            _run_pi_smoke_eval(config_path, logbook_dir, workspace_path)
            _run_smoke_readiness_report(logbook_dir)

            report = render_smoke_report(logbook_dir)

            self.assertEqual(
                report,
                "\n".join(
                    [
                        "Real smoke report: pi-fff-comparison / swe-bench-lite",
                        "Status: ready",
                        "Vessels: 2 | Ready: 2 | Blocked: 0 | Attempts: 2 | "
                        "Failed: 0 | Distinct tools: 2 | Tokens: 100 | Cost: -",
                        f"Artifacts: logbook={logbook_dir} | "
                        f"readiness={logbook_dir / 'smoke-readiness-report.json'} | "
                        f"scorecard={logbook_dir / 'task-attempt-scorecard.json'} | "
                        f"report={logbook_dir / 'smoke-report.txt'}",
                        "",
                        "comparison | vessel | status | preflight | attempts | "
                        "tools | expected | missing | tokens | cost | details",
                        "pi-vs-pi-fff | pi-baseline | ready | passed | measured | "
                        "fffind:1 | - | - | 45 | - | -",
                        "pi-vs-pi-fff | pi-plus-fff | ready | passed | measured | "
                        "fffind:1 | fffind | - | 55 | - | -",
                        "",
                    ]
                ),
            )

    def test_smoke_report_command_writes_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)
            output_path = root / "reports" / "smoke.md"
            _write_passed_preflights(logbook_dir)
            _run_pi_smoke_eval(config_path, logbook_dir, workspace_path)
            _run_smoke_readiness_report(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "markdown",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "| pi-vs-pi-fff | pi-plus-fff | ready | passed | measured | "
                "fffind:1 | fffind | - | 55 | - | - |",
                output_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                f"- Smoke report: `{logbook_dir / 'smoke-report.txt'}`",
                output_path.read_text(encoding="utf-8"),
            )


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    logbook_dir = root / "logbook"
    config_path.write_text(
        PI_WITH_FFF_CONFIG.replace(
            PI_FFF_TYPED_INSTALL,
            "install = []\n",
        ),
        encoding="utf-8",
    )
    workspace_path.mkdir()
    return config_path, workspace_path, logbook_dir


def _write_passed_preflights(logbook_dir: Path) -> None:
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


def _run_pi_smoke_eval(
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> None:
    def runner(request: PiTaskRequest) -> CommandResult:
        return CommandResult(
            exit_code=0,
            stdout=json.dumps({"completed": True, "tool_calls": ["fffind"]}),
            stderr="",
        )

    with (
        patch(
            "yacht.harnesses.registry.SubprocessPiTaskLauncher",
            return_value=SubprocessPiTaskLauncher(runner=runner),
        ),
        patch(
            "yacht.courses.registry.SweBenchAdapter.task_with_context",
            autospec=True,
            side_effect=lambda self, *, task, adapter: task,
        ),
        patch(
            "yacht.courses.registry.SweBenchAdapter.workspace_for_attempt",
            autospec=True,
            return_value=workspace_path,
        ),
        redirect_stdout(StringIO()),
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
        if exit_code == 0:
            exit_code = main(
                [
                    "internals",
                    "task-attempt-scorecard",
                    "--logbook",
                    str(logbook_dir),
                ]
            )
    if exit_code != 0:
        raise AssertionError(f"pi smoke setup exited {exit_code}")


def _run_smoke_readiness_report(logbook_dir: Path) -> None:
    with redirect_stdout(StringIO()):
        exit_code = main(
            ["internals", "smoke-readiness-report", "--logbook", str(logbook_dir)]
        )
    if exit_code != 0:
        raise AssertionError(f"smoke-readiness-report exited {exit_code}")


if __name__ == "__main__":
    unittest.main()
