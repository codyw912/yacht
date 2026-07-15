import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.benchmark_fixtures import write_vessel_ready_inputs
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.workflows.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.cli import main
from yacht.domain.model import ConfigError
from yacht.courses.swe_bench.grading import write_swe_bench_grading_report
from yacht.courses.swe_bench.predictions import write_swe_bench_predictions


VALID_NATIVE_REPORT = {
    "total_instances": 1,
    "submitted_instances": 1,
    "completed_instances": 1,
    "resolved_instances": 1,
    "unresolved_instances": 0,
    "empty_patch_instances": 0,
    "error_instances": 0,
    "submitted_ids": ["django__django-11099"],
    "completed_ids": ["django__django-11099"],
    "incomplete_ids": [],
    "resolved_ids": ["django__django-11099"],
    "unresolved_ids": [],
    "empty_patch_ids": [],
    "error_ids": [],
    "schema_version": 2,
}


class SweBenchGradingTests(unittest.TestCase):
    def test_write_grading_report_validates_native_report_and_writes_artifact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            native_report_path = root / "native-report.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            native_report_path.write_text(
                json.dumps(VALID_NATIVE_REPORT),
                encoding="utf-8",
            )
            write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            summary = write_swe_bench_grading_report(
                config_path=config_path,
                native_report_path=native_report_path,
                logbook_dir=logbook_dir,
            )

            self.assertEqual(summary["status"], "validated")
            self.assertEqual(summary["adapter"], "swe-bench")
            self.assertEqual(summary["submitted_instances"], 1)
            self.assertEqual(summary["resolved_instances"], 1)
            self.assertEqual(summary["resolution_rate"], 1.0)
            grading_path = logbook_dir / "course-handoff/swe-bench/grading-report.json"
            self.assertEqual(summary["grading_report_path"], str(grading_path))
            artifact = json.loads(grading_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["schema"], "yacht.swe-bench-grading.v1")
            self.assertEqual(artifact["native_report"], VALID_NATIVE_REPORT)
            self.assertEqual(
                artifact["candidate_patches_path"],
                str(logbook_dir / "course-handoff/swe-bench/candidate-patches.jsonl"),
            )

    def test_rejects_report_for_ids_not_in_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            native_report_path = root / "native-report.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            native_report_path.write_text(
                json.dumps(
                    VALID_NATIVE_REPORT
                    | {
                        "submitted_ids": ["django__django-99999"],
                    }
                ),
                encoding="utf-8",
            )
            write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            with self.assertRaisesRegex(
                ConfigError,
                "grading report submitted_ids contains task outside course handoff",
            ):
                write_swe_bench_grading_report(
                    config_path=config_path,
                    native_report_path=native_report_path,
                    logbook_dir=logbook_dir,
                )

            self.assertFalse(
                (logbook_dir / "course-handoff/swe-bench/grading-report.json").exists()
            )

    def test_rejects_report_that_does_not_match_candidate_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            native_report_path = root / "native-report.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            native_report_path.write_text(
                json.dumps(VALID_NATIVE_REPORT | {"submitted_ids": []}),
                encoding="utf-8",
            )
            write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            with self.assertRaisesRegex(
                ConfigError,
                "grading report submitted_ids must match candidate patch instance_ids",
            ):
                write_swe_bench_grading_report(
                    config_path=config_path,
                    native_report_path=native_report_path,
                    logbook_dir=logbook_dir,
                )

    def test_grading_report_command_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            native_report_path = root / "native-report.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            native_report_path.write_text(
                json.dumps(VALID_NATIVE_REPORT),
                encoding="utf-8",
            )
            write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "grading-report",
                        str(config_path),
                        "--input",
                        str(native_report_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "validated")
            self.assertEqual(payload["resolved_instances"], 1)
            self.assertTrue(
                (logbook_dir / "course-handoff/swe-bench/grading-report.json").is_file()
            )

    def test_grading_report_command_writes_vessel_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            native_report_path = root / "native-report.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            native_report_path.write_text(
                json.dumps(VALID_NATIVE_REPORT),
                encoding="utf-8",
            )
            write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "grading-report",
                        str(config_path),
                        "--input",
                        str(native_report_path),
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["vessel"], "pi-plus-fff")
            grading_path = (
                logbook_dir
                / "course-handoff/swe-bench/vessels/pi-plus-fff/grading-report.json"
            )
            self.assertEqual(payload["grading_report_path"], str(grading_path))
            artifact = json.loads(grading_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["vessel"], "pi-plus-fff")
            self.assertEqual(
                artifact["candidate_patches_path"],
                str(
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-plus-fff/candidate-patches.jsonl"
                ),
            )

    def test_grading_report_command_can_read_native_report_from_launcher(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            write_vessel_ready_inputs(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root / "workspace",
                vessel_name="pi-plus-fff",
            )
            launcher_handoff = write_benchmark_launcher_handoff(
                logbook_dir=logbook_dir,
                python_executable="uv run python",
            )
            native_report_path = _expected_launcher_native_report_path(
                launcher_handoff,
                "pi-plus-fff",
            )
            native_report_path.parent.mkdir(parents=True, exist_ok=True)
            native_report_path.write_text(
                json.dumps(VALID_NATIVE_REPORT),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "grading-report",
                        str(config_path),
                        "--from-launcher",
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["vessel"], "pi-plus-fff")
            self.assertEqual(payload["resolved_instances"], 1)
            grading_path = (
                logbook_dir
                / "course-handoff/swe-bench/vessels/pi-plus-fff/grading-report.json"
            )
            artifact = json.loads(grading_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["source_report_path"], str(native_report_path))

    def test_grading_report_from_launcher_reports_missing_native_report(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            write_vessel_ready_inputs(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root / "workspace",
                vessel_name="pi-plus-fff",
            )
            write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "grading-report",
                        str(config_path),
                        "--from-launcher",
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: native SWE-bench report not found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_grading_report_from_launcher_requires_vessel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "grading-report",
                        str(config_path),
                        "--from-launcher",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: --from-launcher requires --vessel",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_grading_report_command_reports_config_errors_without_traceback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            native_report_path = root / "native-report.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            native_report_path.write_text(
                json.dumps(VALID_NATIVE_REPORT),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "grading-report",
                        str(config_path),
                        "--input",
                        str(native_report_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: candidate patches file not found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_example_native_report_matches_candidate_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_swe_bench_predictions(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            summary = write_swe_bench_grading_report(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                native_report_path=Path("examples/pi-fff-native-report.json"),
                logbook_dir=logbook_dir,
            )

            self.assertEqual(summary["resolved_instances"], 1)
            self.assertEqual(summary["resolution_rate"], 1.0)


def _expected_launcher_native_report_path(
    launcher_handoff: dict[str, object],
    vessel_name: str,
) -> Path:
    for comparison in launcher_handoff["comparisons"]:
        for vessel in comparison["vessels"]:
            if vessel["name"] == vessel_name:
                command = vessel["command"]
                run_id = command[command.index("--run_id") + 1]
                return (
                    Path(vessel["native_report_dir"]) / f"{vessel_name}.{run_id}.json"
                )
    raise AssertionError(f"missing vessel {vessel_name}")


if __name__ == "__main__":
    unittest.main()
