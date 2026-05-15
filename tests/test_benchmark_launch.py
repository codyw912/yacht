import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.benchmark_fixtures import PI_FFF_CONFIG_PATH
from tests.benchmark_fixtures import PI_FFF_PREDICTIONS_PATH
from tests.benchmark_fixtures import write_runtime_snapshot
from tests.benchmark_fixtures import write_vessel_candidate
from tests.benchmark_fixtures import write_vessel_preflight
from yacht.benchmark_launch import write_benchmark_launch_result
from yacht.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.cli import main
from yacht.course_handoff import write_course_handoff
from yacht.preflight import CommandResult
from yacht.swebench_predictions import write_swe_bench_predictions


class BenchmarkLaunchTests(unittest.TestCase):
    def test_launch_executes_ready_native_commands_and_records_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_ready_logbook(Path(temp_dir))
            write_benchmark_launcher_handoff(
                logbook_dir=logbook_dir,
                python_executable="python",
            )
            calls = []

            def runner(argv: list[str], cwd: Path) -> CommandResult:
                calls.append((argv, cwd))
                return CommandResult(
                    exit_code=0,
                    stdout=f"ran {argv[-1]}\n",
                    stderr="native stderr\n",
                )

            result = write_benchmark_launch_result(
                logbook_dir=logbook_dir,
                command_runner=runner,
            )

            self.assertEqual(result["schema"], "yacht.benchmark-launch-result.v1")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["summary"]["launched_vessels"], 2)
            self.assertEqual(result["summary"]["failed_launches"], 0)
            self.assertEqual(len(calls), 2)
            vessel = result["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["name"], "pi-baseline")
            self.assertEqual(vessel["status"], "completed")
            self.assertEqual(vessel["exit_code"], 0)
            self.assertTrue(Path(vessel["stdout_path"]).is_file())
            self.assertTrue(Path(vessel["stderr_path"]).is_file())
            self.assertIn(
                "ran django__django-11099",
                Path(vessel["stdout_path"]).read_text(),
            )
            self.assertEqual(Path(vessel["stderr_path"]).read_text(), "native stderr\n")
            self.assertEqual(
                json.loads(
                    (logbook_dir / "benchmark-launch-result.json").read_text(
                        encoding="utf-8"
                    )
                ),
                result,
            )

    def test_benchmark_launch_command_writes_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_ready_logbook(Path(temp_dir))
            write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            stdout = StringIO()
            with patch(
                "yacht.benchmark_launch._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), redirect_stdout(stdout):
                exit_code = main(["benchmark-launch", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-launch-result.v1")
            self.assertEqual(payload["status"], "complete")
            self.assertTrue((logbook_dir / "benchmark-launch-result.json").is_file())

    def test_launch_blocks_when_no_vessels_are_ready_to_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_course_handoff(PI_FFF_CONFIG_PATH, logbook_dir)
            write_benchmark_launcher_handoff(logbook_dir=logbook_dir)
            calls = []

            def runner(argv: list[str], cwd: Path) -> CommandResult:
                calls.append((argv, cwd))
                return CommandResult(exit_code=0, stdout="", stderr="")

            result = write_benchmark_launch_result(
                logbook_dir=logbook_dir,
                command_runner=runner,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["summary"]["launched_vessels"], 0)
            self.assertEqual(result["summary"]["skipped_vessels"], 2)
            self.assertEqual(calls, [])
            vessel = result["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["status"], "skipped")
            self.assertEqual(vessel["skipped_reason"], "missing-candidate-patches")


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
    write_swe_bench_predictions(
        config_path=PI_FFF_CONFIG_PATH,
        predictions_path=PI_FFF_PREDICTIONS_PATH,
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-plus-fff")
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
