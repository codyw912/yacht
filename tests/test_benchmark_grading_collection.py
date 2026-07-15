import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.benchmark_fixtures import PI_FFF_CONFIG_PATH
from tests.benchmark_fixtures import write_runtime_snapshot
from tests.benchmark_fixtures import write_vessel_candidate
from tests.benchmark_fixtures import write_vessel_preflight
from yacht.workflows.benchmark_grading_collection import (
    collect_benchmark_grading_reports,
)
from yacht.workflows.benchmark_launch import write_benchmark_launch_result
from yacht.workflows.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.cli import main
from yacht.preflight import CommandResult


class BenchmarkGradingCollectionTests(unittest.TestCase):
    def test_collects_completed_launch_reports_into_vessel_grading_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = _prepared_ready_logbook(root)
            write_benchmark_launcher_handoff(
                logbook_dir=logbook_dir,
                python_executable="python",
            )
            launch_result = write_benchmark_launch_result(
                logbook_dir=logbook_dir,
                command_runner=lambda _argv, _cwd: CommandResult(
                    exit_code=0,
                    stdout="ok\n",
                    stderr="",
                ),
            )
            _write_native_report(
                launch_result,
                vessel_name="pi-baseline",
                source_path=Path("examples/pi-baseline-native-report.json"),
            )
            _write_native_report(
                launch_result,
                vessel_name="pi-plus-fff",
                source_path=Path("examples/pi-fff-native-report.json"),
            )

            summary = collect_benchmark_grading_reports(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
            )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["summary"]["collected_reports"], 2)
            self.assertEqual(summary["summary"]["missing_native_reports"], 0)
            self.assertEqual(
                summary["next_steps"][0]["command"],
                [
                    "uv",
                    "run",
                    "yacht",
                    "benchmark-scorecard",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
            self.assertEqual(
                [vessel["status"] for vessel in summary["comparisons"][0]["vessels"]],
                ["collected", "collected"],
            )
            baseline_path = (
                logbook_dir
                / "course-handoff/swe-bench/vessels/pi-baseline/grading-report.json"
            )
            fff_path = (
                logbook_dir
                / "course-handoff/swe-bench/vessels/pi-plus-fff/grading-report.json"
            )
            self.assertTrue(baseline_path.is_file())
            self.assertTrue(fff_path.is_file())
            self.assertEqual(
                json.loads(baseline_path.read_text(encoding="utf-8"))["vessel"],
                "pi-baseline",
            )
            self.assertEqual(
                json.loads(
                    (logbook_dir / "benchmark-grading-collection.json").read_text(
                        encoding="utf-8"
                    )
                ),
                summary,
            )

    def test_benchmark_collect_grading_command_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = _prepared_ready_logbook(root)
            write_benchmark_launcher_handoff(logbook_dir=logbook_dir)
            launch_result = write_benchmark_launch_result(
                logbook_dir=logbook_dir,
                command_runner=lambda _argv, _cwd: CommandResult(
                    exit_code=0,
                    stdout="ok\n",
                    stderr="",
                ),
            )
            _write_native_report(
                launch_result,
                vessel_name="pi-baseline",
                source_path=Path("examples/pi-baseline-native-report.json"),
            )
            _write_native_report(
                launch_result,
                vessel_name="pi-plus-fff",
                source_path=Path("examples/pi-fff-native-report.json"),
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-collect-grading",
                        str(PI_FFF_CONFIG_PATH),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["summary"]["collected_reports"], 2)

    def test_records_missing_native_reports_without_writing_grading_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = _prepared_ready_logbook(root)
            write_benchmark_launcher_handoff(logbook_dir=logbook_dir)
            launch_result = write_benchmark_launch_result(
                logbook_dir=logbook_dir,
                command_runner=lambda _argv, _cwd: CommandResult(
                    exit_code=0,
                    stdout="ok\n",
                    stderr="",
                ),
            )
            _write_native_report(
                launch_result,
                vessel_name="pi-baseline",
                source_path=Path("examples/pi-baseline-native-report.json"),
            )

            summary = collect_benchmark_grading_reports(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
            )

            self.assertEqual(summary["status"], "partial")
            self.assertEqual(summary["summary"]["collected_reports"], 1)
            self.assertEqual(summary["summary"]["missing_native_reports"], 1)
            self.assertEqual(
                [step["label"] for step in summary["next_steps"]],
                ["Write benchmark scorecard", "Rerun benchmark launch"],
            )
            missing_vessel = summary["comparisons"][0]["vessels"][1]
            self.assertEqual(missing_vessel["name"], "pi-plus-fff")
            self.assertEqual(missing_vessel["status"], "missing-native-report")
            self.assertIn("native SWE-bench report not found", missing_vessel["error"])
            self.assertFalse(
                (
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-plus-fff/grading-report.json"
                ).exists()
            )


def _prepared_ready_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_vessel_candidate(
        config_path=PI_FFF_CONFIG_PATH,
        logbook_dir=logbook_dir,
        vessel_name="pi-baseline",
    )
    write_runtime_snapshot(
        config_path=PI_FFF_CONFIG_PATH,
        logbook_dir=logbook_dir,
        workspace_path=root / "workspace",
    )
    write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-baseline")
    write_vessel_candidate(
        config_path=PI_FFF_CONFIG_PATH,
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-plus-fff")
    return logbook_dir


def _write_native_report(
    launch_result: dict[str, object],
    *,
    vessel_name: str,
    source_path: Path,
) -> None:
    for comparison in launch_result["comparisons"]:
        for vessel in comparison["vessels"]:
            if vessel["name"] == vessel_name:
                command = vessel["command"]
                run_id = command[command.index("--run_id") + 1]
                native_report_path = (
                    Path(vessel["native_report_dir"]) / f"{vessel_name}.{run_id}.json"
                )
                native_report_path.write_text(
                    source_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                return
    raise AssertionError(f"missing vessel {vessel_name}")


if __name__ == "__main__":
    unittest.main()
