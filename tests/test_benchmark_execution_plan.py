import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.benchmark_fixtures import PI_FFF_CONFIG_PATH
from tests.benchmark_fixtures import PI_FFF_PREDICTIONS_PATH
from tests.benchmark_fixtures import write_pi_fff_config
from tests.benchmark_fixtures import write_runtime_snapshot
from tests.benchmark_fixtures import write_vessel_candidate
from tests.benchmark_fixtures import write_vessel_preflight
from tests.benchmark_fixtures import write_vessel_ready_inputs
from yacht.workflows.benchmark_execution_plan import write_benchmark_execution_plan
from yacht.cli import main
from yacht.courses.handoff import write_course_handoff
from yacht.domain.model import ConfigError
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.courses.swe_bench.grading import write_swe_bench_grading_report
from yacht.courses.swe_bench.predictions import write_swe_bench_predictions


class BenchmarkExecutionPlanTests(unittest.TestCase):
    def test_benchmark_execution_plan_reports_missing_candidate_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_course_handoff(
                PI_FFF_CONFIG_PATH,
                logbook_dir,
            )

            plan = write_benchmark_execution_plan(logbook_dir)

            self.assertEqual(plan["schema"], "yacht.benchmark-execution-plan.v1")
            self.assertEqual(plan["regatta"], "pi-fff-comparison")
            self.assertEqual(plan["course"], "swe-bench-lite")
            self.assertEqual(plan["status"], "missing-inputs")
            self.assertEqual(
                plan["comparisons"],
                [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "status": "missing-inputs",
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "status": "missing-candidate-patches",
                                "candidate_patches_path": str(
                                    logbook_dir
                                    / "course-handoff/swe-bench/vessels/pi-baseline/candidate-patches.jsonl"
                                ),
                                "candidate_patches_present": False,
                                "grading_report_path": str(
                                    logbook_dir
                                    / "course-handoff/swe-bench/vessels/pi-baseline/grading-report.json"
                                ),
                                "grading_report_present": False,
                                "preflight_artifact_path": str(
                                    logbook_dir
                                    / "preflight/pi-vs-pi-fff/pi-baseline.json"
                                ),
                                "preflight_artifact_present": False,
                                "preflight_status": "missing",
                                "runtime_instances_artifact_path": str(
                                    logbook_dir / "runtime-instances.json"
                                ),
                                "runtime_instances_artifact_present": False,
                                "runtime_snapshot_status": "missing",
                            },
                            {
                                "name": "pi-plus-fff",
                                "status": "missing-candidate-patches",
                                "candidate_patches_path": str(
                                    logbook_dir
                                    / "course-handoff/swe-bench/vessels/pi-plus-fff/candidate-patches.jsonl"
                                ),
                                "candidate_patches_present": False,
                                "grading_report_path": str(
                                    logbook_dir
                                    / "course-handoff/swe-bench/vessels/pi-plus-fff/grading-report.json"
                                ),
                                "grading_report_present": False,
                                "preflight_artifact_path": str(
                                    logbook_dir
                                    / "preflight/pi-vs-pi-fff/pi-plus-fff.json"
                                ),
                                "preflight_artifact_present": False,
                                "preflight_status": "missing",
                                "runtime_instances_artifact_path": str(
                                    logbook_dir / "runtime-instances.json"
                                ),
                                "runtime_instances_artifact_present": False,
                                "runtime_snapshot_status": "missing",
                            },
                        ],
                    }
                ],
            )
            saved = json.loads(
                (logbook_dir / "benchmark-execution-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved, plan)

    def test_benchmark_execution_plan_reports_ready_and_graded_vessels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_mixed_logbook(Path(temp_dir))

            plan = write_benchmark_execution_plan(logbook_dir)

            self.assertEqual(plan["status"], "mixed")
            vessels = plan["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["status"], "ready-for-grading")
            self.assertTrue(vessels[0]["candidate_patches_present"])
            self.assertFalse(vessels[0]["grading_report_present"])
            self.assertTrue(vessels[0]["preflight_artifact_present"])
            self.assertEqual(vessels[0]["preflight_status"], "passed")
            self.assertEqual(vessels[1]["name"], "pi-plus-fff")
            self.assertEqual(vessels[1]["status"], "graded")
            self.assertTrue(vessels[1]["candidate_patches_present"])
            self.assertTrue(vessels[1]["grading_report_present"])

    def test_benchmark_execution_plan_blocks_candidate_without_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_vessel_candidate(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )

            plan = write_benchmark_execution_plan(logbook_dir)

            vessels = plan["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["status"], "missing-preflight")
            self.assertFalse(vessels[0]["preflight_artifact_present"])
            self.assertEqual(vessels[0]["preflight_status"], "missing")

    def test_benchmark_execution_plan_blocks_candidate_without_runtime_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_vessel_candidate(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )
            write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-baseline")

            plan = write_benchmark_execution_plan(logbook_dir)

            vessels = plan["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["status"], "missing-runtime-snapshot")
            self.assertEqual(
                vessels[0]["runtime_instances_artifact_path"],
                str(logbook_dir / "runtime-instances.json"),
            )
            self.assertFalse(vessels[0]["runtime_instances_artifact_present"])
            self.assertEqual(vessels[0]["runtime_snapshot_status"], "missing")

    def test_benchmark_execution_plan_reports_runtime_snapshot_identity_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            write_pi_fff_config(config_path)
            write_vessel_ready_inputs(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root / "workspace",
                vessel_name="pi-baseline",
            )
            snapshot_path = logbook_dir / RUNTIME_INSTANCES_PLAN_PATH
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["regatta"] = "stale-regatta"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["benchmark-plan", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: runtime instances artifact identity "
                "does not match benchmark handoff:",
                stderr.getvalue(),
            )
            self.assertIn(
                "regatta='stale-regatta', expected 'pi-fff-comparison'",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_execution_plan_blocks_failed_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_vessel_candidate(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )
            write_vessel_preflight(
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
                status="failed",
            )

            plan = write_benchmark_execution_plan(logbook_dir)

            vessels = plan["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["status"], "preflight-failed")
            self.assertTrue(vessels[0]["preflight_artifact_present"])
            self.assertEqual(vessels[0]["preflight_status"], "failed")

    def test_benchmark_execution_plan_command_writes_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_course_handoff(
                PI_FFF_CONFIG_PATH,
                logbook_dir,
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["benchmark-plan", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-execution-plan.v1")
            self.assertEqual(payload["status"], "missing-inputs")
            self.assertTrue((logbook_dir / "benchmark-execution-plan.json").is_file())

    def test_benchmark_execution_plan_command_reports_errors_without_traceback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-plan",
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

    def test_benchmark_execution_plan_requires_handoff_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            with self.assertRaisesRegex(
                ConfigError,
                "course handoff artifact not found",
            ):
                write_benchmark_execution_plan(logbook_dir)

            self.assertFalse((logbook_dir / "benchmark-execution-plan.json").exists())


def _prepared_mixed_logbook(root: Path) -> Path:
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
    write_swe_bench_grading_report(
        config_path=PI_FFF_CONFIG_PATH,
        native_report_path=Path("examples/pi-fff-native-report.json"),
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
