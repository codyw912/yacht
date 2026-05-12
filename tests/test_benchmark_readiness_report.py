import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.benchmark_readiness_report import render_benchmark_readiness_report
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


if __name__ == "__main__":
    unittest.main()
