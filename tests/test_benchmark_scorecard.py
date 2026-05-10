import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.benchmark_scorecard import write_benchmark_scorecard
from yacht.cli import main
from yacht.regatta import ConfigError
from yacht.swebench_grading import write_swe_bench_grading_report
from yacht.swebench_predictions import write_swe_bench_predictions


class BenchmarkScorecardTests(unittest.TestCase):
    def test_write_benchmark_scorecard_summarizes_validated_grading_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))

            scorecard = write_benchmark_scorecard(logbook_dir)

            self.assertEqual(scorecard["schema"], "yacht.benchmark-scorecard.v1")
            self.assertEqual(scorecard["regatta"], "pi-fff-comparison")
            self.assertEqual(scorecard["course"], "swe-bench-lite")
            self.assertEqual(scorecard["status"], "partial")
            self.assertEqual(
                scorecard["adapter"],
                {
                    "kind": "swe-bench",
                    "dataset": "princeton-nlp/SWE-bench_Lite",
                    "split": "test",
                },
            )
            self.assertEqual(
                scorecard["comparisons"],
                [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "status": "missing",
                                "submitted_instances": 0,
                                "resolved_instances": 0,
                                "resolution_rate": 0.0,
                            },
                            {
                                "name": "pi-plus-fff",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 1,
                                "resolution_rate": 1.0,
                                "resolved_ids": ["django__django-11099"],
                                "unresolved_ids": [],
                            },
                        ],
                    }
                ],
            )
            saved = json.loads(
                (logbook_dir / "benchmark-scorecard.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved, scorecard)

    def test_benchmark_scorecard_requires_grading_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_swe_bench_predictions(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            with self.assertRaisesRegex(
                ConfigError,
                "validated grading report not found",
            ):
                write_benchmark_scorecard(logbook_dir)

            self.assertFalse((logbook_dir / "benchmark-scorecard.json").exists())

    def test_benchmark_scorecard_command_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-scorecard",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-scorecard.v1")
            self.assertEqual(payload["status"], "partial")

    def test_benchmark_scorecard_command_reports_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_swe_bench_predictions(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-scorecard",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: validated grading report not found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())


def _prepared_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_swe_bench_predictions(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        predictions_path=Path("examples/pi-fff-predictions.json"),
        logbook_dir=logbook_dir,
    )
    write_swe_bench_grading_report(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        native_report_path=Path("examples/pi-fff-native-report.json"),
        logbook_dir=logbook_dir,
    )
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
