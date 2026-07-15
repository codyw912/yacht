import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from yacht.cli import main
from yacht.logbook.io import write_json
from yacht.reports.smoke_status import build_smoke_status


def _write_smoke_logbook(logbook_dir: Path) -> None:
    write_json(
        logbook_dir / "run-index.json",
        {"schema": "yacht.run-index.v1", "run_kind": "real-smoke"},
    )
    write_json(
        logbook_dir / "smoke-readiness-report.json",
        {"schema": "yacht.smoke-readiness-report.v1", "status": "ready"},
    )


def _write_benchmark_logbook(logbook_dir: Path) -> None:
    write_json(
        logbook_dir / "run-index.json",
        {
            "schema": "yacht.run-index.v1",
            "run_kind": "real-benchmark",
            "status": "complete",
            "regatta": "example",
            "course": "swe-bench-lite",
            "comparisons": [],
            "artifacts": {},
        },
    )


class StatusCommandTests(unittest.TestCase):
    def test_smoke_logbook_renders_smoke_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_smoke_logbook(logbook_dir)
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["status", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 0)
            self.assertIn("Smoke logbook:", stdout.getvalue())
            self.assertIn("Status: ready", stdout.getvalue())

    def test_benchmark_logbook_renders_benchmark_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_benchmark_logbook(logbook_dir)
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["status", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 0)
            self.assertIn("Benchmark", stdout.getvalue())

    def test_missing_logbook_reports_error_with_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "nope"
            stderr = StringIO()

            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = main(["status", "--logbook", str(missing)])

            self.assertEqual(exit_code, 1)
            self.assertIn("logbook directory not found", stderr.getvalue())

    def test_defaults_to_latest_logbook_when_no_local_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            latest = root / "yacht-example"
            _write_smoke_logbook(latest)
            cwd = root / "empty-cwd"
            cwd.mkdir()
            stderr = StringIO()
            stdout = StringIO()

            original_cwd = os.getcwd()
            os.chdir(cwd)
            try:
                with patch(
                    "yacht.cli.commands.inspect.tempfile.gettempdir",
                    return_value=str(root),
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(["status"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0)
            self.assertIn("using latest logbook", stderr.getvalue())
            self.assertIn("Smoke logbook:", stdout.getvalue())


class ReportCommandTests(unittest.TestCase):
    def test_smoke_logbook_routes_to_smoke_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_smoke_logbook(logbook_dir)
            stdout = StringIO()

            with patch(
                "yacht.cli.commands.inspect.render_smoke_report",
                return_value="smoke report\n",
            ) as render:
                with redirect_stdout(stdout):
                    exit_code = main(["report", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 0)
            render.assert_called_once()
            self.assertEqual(stdout.getvalue(), "smoke report\n")

    def test_benchmark_logbook_routes_to_benchmark_report_with_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_benchmark_logbook(logbook_dir)

            with patch(
                "yacht.cli.commands.inspect.render_benchmark_report",
                return_value="benchmark report\n",
            ) as render:
                with redirect_stdout(StringIO()):
                    exit_code = main(
                        [
                            "report",
                            "--logbook",
                            str(logbook_dir),
                            "--vessel",
                            "baseline",
                            "--task",
                            "task-1",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            call = render.call_args
            self.assertEqual(call.kwargs["vessel_name"], "baseline")
            self.assertEqual(call.kwargs["task_id"], "task-1")

    def test_filters_are_rejected_for_smoke_logbooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_smoke_logbook(logbook_dir)
            stderr = StringIO()

            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "baseline",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("apply to benchmark logbooks", stderr.getvalue())

    def test_report_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            output_path = Path(temp_dir) / "out" / "report.md"
            _write_smoke_logbook(logbook_dir)

            with patch(
                "yacht.cli.commands.inspect.render_smoke_report",
                return_value="smoke report\n",
            ):
                with redirect_stdout(StringIO()):
                    exit_code = main(
                        [
                            "report",
                            "--logbook",
                            str(logbook_dir),
                            "--output",
                            str(output_path),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "smoke report\n")


class SmokeStatusBuilderTests(unittest.TestCase):
    def test_reports_missing_artifacts_and_run_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()

            status = build_smoke_status(logbook_dir)

            self.assertEqual(status["status"], "missing")
            self.assertIn("smoke-readiness-report", status["missing"])
            self.assertIn("yacht run", status["next_step"])

    def test_complete_logbook_recommends_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_smoke_logbook(logbook_dir)
            write_json(logbook_dir / "real-smoke-runbook.json", {})
            write_json(logbook_dir / "task-attempt-scorecard.json", {})

            status = build_smoke_status(logbook_dir)

            self.assertEqual(status["status"], "ready")
            self.assertEqual(status["missing"], [])
            self.assertIn("yacht report", status["next_step"])

    def test_json_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_smoke_logbook(logbook_dir)

            status = build_smoke_status(logbook_dir)

            self.assertEqual(json.loads(json.dumps(status)), status)


if __name__ == "__main__":
    unittest.main()
