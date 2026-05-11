import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.preflight_artifacts import write_preflight_artifact
from yacht.benchmark_scorecard import write_benchmark_scorecard
from yacht.cli import main
from yacht.regatta import ConfigError
from yacht.swebench_grading import write_swe_bench_grading_report
from yacht.swebench_predictions import write_swe_bench_predictions


BASELINE_PREDICTIONS = [
    {
        "instance_id": "django__django-11099",
        "model_name_or_path": "pi-baseline",
        "model_patch": "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n",
    }
]
BASELINE_NATIVE_REPORT = {
    "total_instances": 1,
    "submitted_instances": 1,
    "completed_instances": 1,
    "resolved_instances": 0,
    "unresolved_instances": 1,
    "empty_patch_instances": 0,
    "error_instances": 0,
    "submitted_ids": ["django__django-11099"],
    "completed_ids": ["django__django-11099"],
    "incomplete_ids": [],
    "resolved_ids": [],
    "unresolved_ids": ["django__django-11099"],
    "empty_patch_ids": [],
    "error_ids": [],
    "schema_version": 2,
}


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
                        "summary": _comparison_summary(
                            eligible=0,
                            measured=1,
                            missing=1,
                        ),
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "status": "missing",
                                "submitted_instances": 0,
                                "resolved_instances": 0,
                                "resolution_rate": 0.0,
                                **_missing_preflight(logbook_dir, "pi-baseline"),
                            },
                            {
                                "name": "pi-plus-fff",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 1,
                                "resolution_rate": 1.0,
                                "resolved_ids": ["django__django-11099"],
                                "unresolved_ids": [],
                                **_missing_preflight(logbook_dir, "pi-plus-fff"),
                            },
                        ],
                    }
                ],
            )
            saved = json.loads(
                (logbook_dir / "benchmark-scorecard.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved, scorecard)

    def test_write_benchmark_scorecard_combines_per_vessel_grading_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))

            scorecard = write_benchmark_scorecard(logbook_dir)

            self.assertEqual(scorecard["status"], "complete")
            self.assertEqual(
                scorecard["comparisons"],
                [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "summary": _comparison_summary(
                            eligible=0,
                            measured=2,
                            missing=0,
                        ),
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 0,
                                "resolution_rate": 0.0,
                                "resolved_ids": [],
                                "unresolved_ids": ["django__django-11099"],
                                **_missing_preflight(logbook_dir, "pi-baseline"),
                            },
                            {
                                "name": "pi-plus-fff",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 1,
                                "resolution_rate": 1.0,
                                "resolved_ids": ["django__django-11099"],
                                "unresolved_ids": [],
                                **_missing_preflight(logbook_dir, "pi-plus-fff"),
                            },
                        ],
                    }
                ],
            )

    def test_benchmark_scorecard_includes_preflight_eligibility_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="passed",
            )

            scorecard = write_benchmark_scorecard(logbook_dir)

            vessels = scorecard["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["preflight_status"], "missing")
            self.assertEqual(vessels[0]["preflight_reason"], "preflight-missing")
            self.assertFalse(vessels[0]["eligible_for_benchmark"])
            self.assertEqual(vessels[1]["name"], "pi-plus-fff")
            self.assertEqual(vessels[1]["preflight_status"], "passed")
            self.assertEqual(vessels[1]["preflight_reason"], "preflight-passed")
            self.assertTrue(vessels[1]["eligible_for_benchmark"])

    def test_benchmark_scorecard_includes_comparison_summary_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="passed",
            )

            scorecard = write_benchmark_scorecard(logbook_dir)

            self.assertEqual(
                scorecard["comparisons"][0]["summary"],
                {
                    "total_vessels": 2,
                    "eligible_vessels": 1,
                    "blocked_vessels": 1,
                    "measured_vessels": 1,
                    "missing_result_vessels": 1,
                },
            )

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


def _missing_preflight(logbook_dir: Path, vessel_name: str) -> dict[str, object]:
    return {
        "eligible_for_benchmark": False,
        "preflight_status": "missing",
        "preflight_reason": "preflight-missing",
        "preflight_artifact_path": str(
            logbook_dir / "preflight/pi-vs-pi-fff" / f"{vessel_name}.json"
        ),
    }


def _comparison_summary(
    *,
    eligible: int,
    measured: int,
    missing: int,
) -> dict[str, int]:
    return {
        "total_vessels": 2,
        "eligible_vessels": eligible,
        "blocked_vessels": 2 - eligible,
        "measured_vessels": measured,
        "missing_result_vessels": missing,
    }


def _prepared_multi_vessel_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    baseline_predictions_path = root / "baseline-predictions.json"
    baseline_report_path = root / "baseline-native-report.json"
    baseline_predictions_path.write_text(
        json.dumps(BASELINE_PREDICTIONS),
        encoding="utf-8",
    )
    baseline_report_path.write_text(
        json.dumps(BASELINE_NATIVE_REPORT),
        encoding="utf-8",
    )
    write_swe_bench_predictions(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        predictions_path=baseline_predictions_path,
        logbook_dir=logbook_dir,
        vessel_name="pi-baseline",
    )
    write_swe_bench_grading_report(
        config_path=Path("examples/pi-fff-provisioning.toml"),
        native_report_path=baseline_report_path,
        logbook_dir=logbook_dir,
        vessel_name="pi-baseline",
    )
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
