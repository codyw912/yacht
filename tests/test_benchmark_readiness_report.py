import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.workflows.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.reports.benchmark_readiness import render_benchmark_readiness_report
from yacht.cli import main


class BenchmarkReadinessReportTests(unittest.TestCase):
    def test_render_benchmark_readiness_report_shows_spend_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)

            report = render_benchmark_readiness_report(logbook_dir)

            self.assertEqual(
                report,
                "\n".join(
                    [
                        "Benchmark readiness: pi-fff-comparison / swe-bench-lite",
                        "Status: mixed",
                        "",
                        "comparison | vessel | status | candidate | runtime | preflight | grading | details",
                        "pi-vs-pi-fff | pi-baseline | missing-runtime-snapshot | "
                        "present | missing | passed | missing | runtime instances: "
                        "runtime-instances.json; grading report: grading-report.json",
                        "pi-vs-pi-fff | pi-plus-fff | graded | present | matched | "
                        "missing | graded | preflight: preflight/pi-plus-fff.json",
                        "",
                    ]
                ),
            )

    def test_render_benchmark_readiness_report_shows_missing_candidate_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)
            plan_path = logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            baseline = plan["comparisons"][0]["vessels"][0]
            baseline["status"] = "missing-candidate-patches"
            baseline["candidate_patches_present"] = False
            baseline["runtime_instances_artifact_present"] = True
            baseline["runtime_snapshot_status"] = "matched"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            report = render_benchmark_readiness_report(logbook_dir)

            self.assertIn(
                "pi-vs-pi-fff | pi-baseline | missing-candidate-patches | "
                "missing | matched | passed | missing | candidate patches: "
                "candidate-patches.jsonl; grading report: grading-report.json",
                report,
            )

    def test_benchmark_readiness_report_command_writes_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            output_path = root / "readiness.md"
            _write_execution_plan(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
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
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "\n".join(
                    [
                        "## Benchmark readiness",
                        "",
                        "- Regatta: pi-fff-comparison",
                        "- Course: swe-bench-lite",
                        "- Status: mixed",
                        "",
                        "| Comparison | Vessel | Status | Candidate | Runtime | Preflight | Grading | Details |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| pi-vs-pi-fff | pi-baseline | missing-runtime-snapshot | "
                        "present | missing | passed | missing | runtime instances: "
                        "runtime-instances.json; grading report: grading-report.json |",
                        "| pi-vs-pi-fff | pi-plus-fff | graded | present | matched | "
                        "missing | graded | preflight: preflight/pi-plus-fff.json |",
                        "",
                    ]
                ),
            )

    def test_benchmark_readiness_report_command_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-execution-plan.v1")
            self.assertEqual(payload["status"], "mixed")
            baseline = payload["comparisons"][0]["vessels"][0]
            self.assertEqual(baseline["status"], "missing-runtime-snapshot")
            self.assertEqual(
                baseline["runtime_instances_artifact_path"],
                "runtime-instances.json",
            )

    def test_benchmark_readiness_report_command_prints_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "summary-json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(
                payload,
                {
                    "schema": "yacht.benchmark-readiness-summary.v1",
                    "regatta": "pi-fff-comparison",
                    "course": "swe-bench-lite",
                    "status": "mixed",
                    "total_vessels": 2,
                    "launchable_vessels": 0,
                    "graded_vessels": 1,
                    "blocked_vessel_count": 1,
                    "blocked_vessels": [
                        {
                            "comparison": "pi-vs-pi-fff",
                            "vessel": "pi-baseline",
                            "status": "missing-runtime-snapshot",
                            "details": "runtime instances: runtime-instances.json; "
                            "grading report: grading-report.json",
                            "artifact_paths": {
                                "candidate_patches": "candidate-patches.jsonl",
                                "preflight": "preflight/pi-baseline.json",
                                "runtime_instances": "runtime-instances.json",
                                "grading_report": "grading-report.json",
                            },
                        }
                    ],
                },
            )

    def test_benchmark_readiness_report_command_writes_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            output_path = root / "reports" / "readiness-summary.json"
            _write_execution_plan(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "summary-json",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "yacht.benchmark-readiness-summary.v1")
            self.assertEqual(payload["blocked_vessel_count"], 1)
            self.assertEqual(
                payload["blocked_vessels"][0]["artifact_paths"][
                    "runtime_instances"
                ],
                "runtime-instances.json",
            )

    def test_readiness_gate_command_blocks_when_summary_has_blocked_vessels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            output_path = root / "reports" / "readiness-summary.json"
            _write_execution_plan(logbook_dir)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "readiness-gate",
                        "--logbook",
                        str(logbook_dir),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("readiness gate blocked: 1 blocked vessel", stderr.getvalue())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["blocked_vessel_count"], 1)

    def test_readiness_gate_command_passes_when_no_vessels_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)
            _mark_baseline_ready(logbook_dir)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "readiness-gate",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["blocked_vessel_count"], 0)
            self.assertEqual(payload["launchable_vessels"], 1)

    def test_readiness_gate_command_writes_summary_when_no_vessels_are_blocked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            output_path = root / "reports" / "readiness-summary.json"
            _write_execution_plan(logbook_dir)
            _mark_baseline_ready(logbook_dir)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "readiness-gate",
                        "--logbook",
                        str(logbook_dir),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["blocked_vessel_count"], 0)
            self.assertEqual(payload["launchable_vessels"], 1)

    def test_readiness_gate_command_reports_missing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "readiness-gate",
                        "--logbook",
                        str(Path(temp_dir) / "logbook"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark execution plan artifact "
                "not found:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_readiness_gate_command_reports_invalid_plan_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
                "{not json",
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "readiness-gate",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark execution plan artifact "
                "is not valid JSON:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_readiness_gate_command_reports_invalid_plan_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
                json.dumps({"schema": "yacht.benchmark-execution-plan.v1"}),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "readiness-gate",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark execution plan artifact "
                "is invalid:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_readiness_report_command_reports_missing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
                        "--logbook",
                        str(Path(temp_dir) / "logbook"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark execution plan artifact "
                "not found:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_readiness_report_command_reports_invalid_plan_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
                "{not json",
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark execution plan artifact "
                "is not valid JSON:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_readiness_report_command_reports_invalid_plan_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
                json.dumps({"schema": "yacht.benchmark-execution-plan.v1"}),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-readiness-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark execution plan artifact "
                "is invalid:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())


def _write_execution_plan(logbook_dir: Path) -> None:
    logbook_dir.mkdir(parents=True)
    plan = {
        "schema": "yacht.benchmark-execution-plan.v1",
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "adapter": {
            "kind": "swe-bench",
            "dataset": "princeton-nlp/SWE-bench_Lite",
            "split": "test",
            "harness": "docker",
        },
        "status": "mixed",
        "comparisons": [
            {
                "name": "pi-vs-pi-fff",
                "course": "swe-bench-lite",
                "status": "mixed",
                "vessels": [
                    {
                        "name": "pi-baseline",
                        "status": "missing-runtime-snapshot",
                        "candidate_patches_path": "candidate-patches.jsonl",
                        "candidate_patches_present": True,
                        "grading_report_path": "grading-report.json",
                        "grading_report_present": False,
                        "preflight_artifact_path": "preflight/pi-baseline.json",
                        "preflight_artifact_present": True,
                        "preflight_status": "passed",
                        "runtime_instances_artifact_path": "runtime-instances.json",
                        "runtime_instances_artifact_present": False,
                        "runtime_snapshot_status": "missing",
                    },
                    {
                        "name": "pi-plus-fff",
                        "status": "graded",
                        "candidate_patches_path": "candidate-patches.jsonl",
                        "candidate_patches_present": True,
                        "grading_report_path": "grading-report.json",
                        "grading_report_present": True,
                        "preflight_artifact_path": "preflight/pi-plus-fff.json",
                        "preflight_artifact_present": False,
                        "preflight_status": "missing",
                        "runtime_instances_artifact_path": "runtime-instances.json",
                        "runtime_instances_artifact_present": True,
                        "runtime_snapshot_status": "matched",
                    },
                ],
            }
        ],
    }
    (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
        json.dumps(plan),
        encoding="utf-8",
    )


def _mark_baseline_ready(logbook_dir: Path) -> None:
    plan_path = logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    baseline = plan["comparisons"][0]["vessels"][0]
    baseline["status"] = "ready-for-grading"
    baseline["runtime_instances_artifact_present"] = True
    baseline["runtime_snapshot_status"] = "matched"
    plan["comparisons"][0]["status"] = "mixed"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
