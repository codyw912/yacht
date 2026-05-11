import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.preflight_artifacts import write_preflight_artifact
from yacht.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.cli import main
from yacht.course_handoff import write_course_handoff
from yacht.regatta import ConfigError
from yacht.swebench_grading import write_swe_bench_grading_report
from yacht.swebench_predictions import write_swe_bench_predictions


class BenchmarkLauncherHandoffTests(unittest.TestCase):
    def test_launcher_handoff_writes_ready_swe_bench_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_ready_logbook(Path(temp_dir))

            handoff = write_benchmark_launcher_handoff(
                logbook_dir=logbook_dir,
                max_workers=2,
                python_executable="uv run python",
            )

            self.assertEqual(handoff["schema"], "yacht.benchmark-launcher-handoff.v1")
            self.assertEqual(handoff["regatta"], "pi-fff-comparison")
            self.assertEqual(handoff["course"], "swe-bench-lite")
            self.assertEqual(handoff["status"], "ready-to-launch")
            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["name"], "pi-baseline")
            self.assertEqual(vessel["status"], "ready-to-launch")
            self.assertEqual(
                vessel["preflight_artifact_path"],
                str(logbook_dir / "preflight/pi-vs-pi-fff/pi-baseline.json"),
            )
            self.assertTrue(vessel["preflight_artifact_present"])
            self.assertEqual(vessel["preflight_status"], "passed")
            self.assertEqual(
                vessel["command"],
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "swebench.harness.run_evaluation",
                    "--dataset_name",
                    "princeton-nlp/SWE-bench_Lite",
                    "--split",
                    "test",
                    "--predictions_path",
                    str(
                        logbook_dir
                        / "course-handoff/swe-bench/vessels/pi-baseline/candidate-patches.jsonl"
                    ),
                    "--max_workers",
                    "2",
                    "--run_id",
                    "pi-fff-comparison__pi-vs-pi-fff__pi-baseline",
                    "--report_dir",
                    str(
                        logbook_dir
                        / "course-handoff/swe-bench/vessels/pi-baseline/native-report"
                    ),
                    "--instance_ids",
                    "django__django-11099",
                ],
            )
            self.assertEqual(
                vessel["command_preview"],
                "uv run python -m swebench.harness.run_evaluation "
                "--dataset_name princeton-nlp/SWE-bench_Lite --split test "
                f"--predictions_path {logbook_dir}/course-handoff/swe-bench/vessels/pi-baseline/candidate-patches.jsonl "
                "--max_workers 2 --run_id pi-fff-comparison__pi-vs-pi-fff__pi-baseline "
                f"--report_dir {logbook_dir}/course-handoff/swe-bench/vessels/pi-baseline/native-report "
                "--instance_ids django__django-11099",
            )
            self.assertEqual(
                vessel["expected_yacht_grading_report_path"],
                str(
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-baseline/grading-report.json"
                ),
            )
            saved = json.loads(
                (logbook_dir / "benchmark-launcher-handoff.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved, handoff)

    def test_launcher_handoff_reports_missing_and_already_graded_vessels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_mixed_logbook(Path(temp_dir))

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            self.assertEqual(handoff["status"], "mixed")
            vessels = handoff["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["status"], "missing-candidate-patches")
            self.assertEqual(vessels[0]["preflight_status"], "missing")
            self.assertNotIn("command", vessels[0])
            self.assertEqual(vessels[1]["name"], "pi-plus-fff")
            self.assertEqual(vessels[1]["status"], "already-graded")
            self.assertNotIn("command", vessels[1])

    def test_launcher_handoff_blocks_candidate_without_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_swe_bench_predictions(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                predictions_path=Path("examples/pi-baseline-predictions.json"),
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["name"], "pi-baseline")
            self.assertEqual(vessel["status"], "missing-preflight")
            self.assertFalse(vessel["preflight_artifact_present"])
            self.assertEqual(vessel["preflight_status"], "missing")
            self.assertNotIn("command", vessel)

    def test_launcher_handoff_blocks_failed_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_swe_bench_predictions(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                predictions_path=Path("examples/pi-baseline-predictions.json"),
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="failed",
            )

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["status"], "preflight-failed")
            self.assertTrue(vessel["preflight_artifact_present"])
            self.assertEqual(vessel["preflight_status"], "failed")
            self.assertNotIn("command", vessel)

    def test_launcher_handoff_command_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_ready_logbook(Path(temp_dir))

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-launcher",
                        "--logbook",
                        str(logbook_dir),
                        "--max-workers",
                        "3",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-launcher-handoff.v1")
            self.assertEqual(payload["status"], "ready-to-launch")
            command = payload["comparisons"][0]["vessels"][0]["command"]
            self.assertIn("--max_workers", command)
            self.assertIn("3", command)
            self.assertTrue((logbook_dir / "benchmark-launcher-handoff.json").is_file())

    def test_launcher_handoff_command_reports_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-launcher",
                        "--logbook",
                        str(Path(temp_dir) / "logbook"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: course handoff artifact not found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_launcher_handoff_requires_handoff_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            with self.assertRaisesRegex(
                ConfigError,
                "course handoff artifact not found",
            ):
                write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            self.assertFalse(
                (logbook_dir / "benchmark-launcher-handoff.json").exists()
            )


def _prepared_ready_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_swe_bench_predictions(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        predictions_path=Path("examples/pi-baseline-predictions.json"),
        logbook_dir=logbook_dir,
        vessel_name="pi-baseline",
    )
    write_preflight_artifact(
        logbook_dir=logbook_dir,
        comparison_name="pi-vs-pi-fff",
        vessel_name="pi-baseline",
        status="passed",
    )
    write_swe_bench_predictions(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        predictions_path=Path("examples/pi-fff-predictions.json"),
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    write_preflight_artifact(
        logbook_dir=logbook_dir,
        comparison_name="pi-vs-pi-fff",
        vessel_name="pi-plus-fff",
        status="passed",
    )
    return logbook_dir


def _prepared_mixed_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_course_handoff(Path("examples/pi-fff-provisioning.toml"), logbook_dir)
    write_swe_bench_predictions(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        predictions_path=Path("examples/pi-fff-predictions.json"),
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    write_swe_bench_grading_report(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        native_report_path=Path("examples/pi-fff-native-report.json"),
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
