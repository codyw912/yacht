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
                scorecard["next_steps"][0]["command"],
                [
                    "uv",
                    "run",
                    "yacht",
                    "benchmark-report",
                    "--logbook",
                    str(logbook_dir),
                ],
            )
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
                        "delta": _comparison_delta(
                            resolved_instances_delta=1,
                            resolution_rate_delta=1.0,
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
                        "delta": _comparison_delta(
                            resolved_instances_delta=1,
                            resolution_rate_delta=1.0,
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

    def test_benchmark_scorecard_includes_top_level_summary_counts(self) -> None:
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
                scorecard["summary"],
                {
                    "total_comparisons": 1,
                    "total_vessels": 2,
                    "eligible_vessels": 1,
                    "blocked_vessels": 1,
                    "measured_vessels": 1,
                    "missing_result_vessels": 1,
                },
            )

    def test_benchmark_scorecard_includes_comparison_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))

            scorecard = write_benchmark_scorecard(logbook_dir)

            self.assertEqual(
                scorecard["comparisons"][0]["delta"],
                {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": "pi-plus-fff",
                    "resolved_instances_delta": 1,
                    "resolution_rate_delta": 1.0,
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
            self.assertEqual(
                payload["next_steps"][0]["command_preview"],
                f"uv run yacht benchmark-report --logbook {logbook_dir}",
            )
            self.assertEqual(
                payload["next_steps"][1]["command_preview"],
                (
                    f"uv run yacht benchmark-report --logbook {logbook_dir} "
                    "--vessel pi-plus-fff --task django__django-11099"
                ),
            )

    def test_benchmark_report_command_prints_comparison_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "\n".join(
                    [
                        "Benchmark scorecard: pi-fff-comparison / swe-bench-lite",
                        "Status: complete",
                        "Comparisons: 1 | Vessels: 2 | Measured: 2 | Missing: 0",
                        "Usage: unavailable (missing task-attempt-scorecard.json)",
                        f"Artifacts: logbook={logbook_dir} | "
                        f"scorecard={logbook_dir / 'benchmark-scorecard.json'} | "
                        f"attempts={logbook_dir / 'task-attempt-scorecard.json'} | "
                        f"launch={logbook_dir / 'benchmark-launch-result.json'} | "
                        "grading="
                        f"{logbook_dir / 'benchmark-grading-collection.json'}",
                        "",
                        "comparison | baseline | challenger | resolved_delta | "
                        "rate_delta | measured | missing | eligible | preflight",
                        "pi-vs-pi-fff | pi-baseline | pi-plus-fff | +1 | +1.000 | "
                        "2/2 | 0 | 0 | preflight-missing:2",
                        "",
                        "Benchmark outcomes by vessel:",
                        "comparison | vessel | status | submitted | resolved | "
                        "rate | preflight",
                        "pi-vs-pi-fff | pi-baseline | measured | 1 | 0 | 0.000 | "
                        "preflight-missing",
                        "pi-vs-pi-fff | pi-plus-fff | measured | 1 | 1 | 1.000 | "
                        "preflight-missing",
                        "",
                    ]
                ),
            )

    def test_benchmark_report_command_prints_markdown_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "\n".join(
                    [
                        "## Benchmark scorecard",
                        "",
                        "- Regatta: pi-fff-comparison",
                        "- Course: swe-bench-lite",
                        "- Status: complete",
                        "- Comparisons: 1",
                        "- Vessels: 2",
                        "- Measured: 2",
                        "- Missing: 0",
                        "- Usage: unavailable (missing task-attempt-scorecard.json)",
                        "",
                        "## Artifacts",
                        "",
                        f"- Logbook: {logbook_dir}",
                        f"- Benchmark scorecard: {logbook_dir / 'benchmark-scorecard.json'}",
                        f"- Task attempt scorecard: {logbook_dir / 'task-attempt-scorecard.json'}",
                        f"- Launch result: {logbook_dir / 'benchmark-launch-result.json'}",
                        "- Grading collection: "
                        f"{logbook_dir / 'benchmark-grading-collection.json'}",
                        "",
                        "| Comparison | Baseline | Challenger | Resolved delta | "
                        "Rate delta | Measured | Missing | Eligible | Preflight |",
                        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
                        "| pi-vs-pi-fff | pi-baseline | pi-plus-fff | +1 | +1.000 | "
                        "2/2 | 0 | 0 | preflight-missing:2 |",
                        "",
                        "## Benchmark outcomes by vessel",
                        "",
                        "| Comparison | Vessel | Status | Submitted | Resolved | Rate | Preflight |",
                        "| --- | --- | --- | ---: | ---: | ---: | --- |",
                        "| pi-vs-pi-fff | pi-baseline | measured | 1 | 0 | 0.000 | "
                        "preflight-missing |",
                        "| pi-vs-pi-fff | pi-plus-fff | measured | 1 | 1 | 1.000 | "
                        "preflight-missing |",
                        "",
                    ]
                ),
            )

    def test_benchmark_report_includes_agent_usage_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)
            _write_task_attempt_scorecard(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn(
                "Usage: Attempts: 2 | Failed: 0 | Tool calls: 7 | "
                "Tokens: 15643 | Cost: 0.010336 | Duration: 12.500s",
                stdout.getvalue(),
            )
            self.assertIn("Agent usage by vessel:", stdout.getvalue())
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | 1 | 0 | bash:1, edit:1, "
                "fffind:1, read:1 | 6251 | 0.004513 | 5.250s",
                stdout.getvalue(),
            )
            self.assertIn("Benchmark task outcomes by vessel:", stdout.getvalue())
            self.assertIn(
                "pi-vs-pi-fff | pi-baseline | django__django-11099 | "
                "unresolved | "
                "logbook/task-attempts/pi-vs-pi-fff/pi-baseline/"
                "django__django-11099.json",
                stdout.getvalue(),
            )
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | django__django-11099 | "
                "resolved | "
                "logbook/task-attempts/pi-vs-pi-fff/pi-plus-fff/"
                "django__django-11099.json",
                stdout.getvalue(),
            )
            self.assertIn("Benchmark artifacts by vessel:", stdout.getvalue())
            self.assertIn(
                str(
                    logbook_dir
                    / "course-handoff"
                    / "swe-bench"
                    / "vessels"
                    / "pi-plus-fff"
                    / "candidate-patches.jsonl"
                ),
                stdout.getvalue(),
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "course-handoff"
                    / "swe-bench"
                    / "vessels"
                    / "pi-plus-fff"
                    / "grading-report.json"
                ),
                stdout.getvalue(),
            )

    def test_benchmark_report_includes_agent_usage_by_task_when_attempts_exist(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)
            _write_task_attempt_scorecard_with_attempt_artifacts(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn("Agent usage by task:", report)
            self.assertIn(
                "comparison | vessel | task | tools | tokens | cost | duration | "
                "attempt_artifact",
                report,
            )
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | django__django-11099 | "
                "bash:1, edit:1, fffind:1, read:1 | 6251 | 0.004513 | "
                "5.250s | "
                f"{logbook_dir}/task-attempts/pi-vs-pi-fff/pi-plus-fff/"
                "django__django-11099.json",
                report,
            )

    def test_benchmark_report_includes_collected_native_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)
            _write_task_attempt_scorecard(logbook_dir)
            _write_grading_collection(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn(
                str(logbook_dir / "native-report" / "pi-plus-fff.json"),
                stdout.getvalue(),
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "course-handoff"
                    / "swe-bench"
                    / "vessels"
                    / "pi-plus-fff"
                    / "grading-report.json"
                ),
                stdout.getvalue(),
            )

    def test_benchmark_report_markdown_includes_drilldown_when_usage_available(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)
            _write_task_attempt_scorecard(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("## Benchmark task outcomes by vessel", stdout.getvalue())
            self.assertNotIn("## Agent usage by task", stdout.getvalue())
            self.assertIn(
                "| pi-vs-pi-fff | pi-plus-fff | django__django-11099 | "
                "resolved | "
                "logbook/task-attempts/pi-vs-pi-fff/pi-plus-fff/"
                "django__django-11099.json |",
                stdout.getvalue(),
            )
            self.assertIn("## Benchmark artifacts by vessel", stdout.getvalue())

    def test_benchmark_report_markdown_includes_agent_usage_by_task_when_attempts_exist(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)
            _write_task_attempt_scorecard_with_attempt_artifacts(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn("## Agent usage by task", report)
            self.assertIn(
                "| pi-vs-pi-fff | pi-plus-fff | django__django-11099 | "
                "bash:1, edit:1, fffind:1, read:1 | 6251 | 0.004513 | "
                "5.250s | "
                f"{logbook_dir}/task-attempts/pi-vs-pi-fff/pi-plus-fff/"
                "django__django-11099.json |",
                report,
            )

    def test_benchmark_report_can_filter_detail_rows_by_vessel_and_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)
            _write_task_attempt_scorecard_with_attempt_artifacts(logbook_dir)
            _write_grading_collection(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                        "--task",
                        "django__django-11099",
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn(
                "Filter: vessel=pi-plus-fff | task=django__django-11099",
                report,
            )
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | measured | 1 | 1 | 1.000 | "
                "preflight-missing",
                report,
            )
            self.assertNotIn(
                "pi-vs-pi-fff | pi-baseline | measured | 1 | 0 | 0.000 | "
                "preflight-missing",
                report,
            )
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | django__django-11099 | "
                "bash:1, edit:1, fffind:1, read:1 | 6251 | 0.004513 | "
                "5.250s | "
                f"{logbook_dir}/task-attempts/pi-vs-pi-fff/pi-plus-fff/"
                "django__django-11099.json",
                report,
            )
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | django__django-11099 | "
                "resolved | "
                f"{logbook_dir}/task-attempts/pi-vs-pi-fff/pi-plus-fff/"
                "django__django-11099.json",
                report,
            )
            self.assertNotIn(
                "logbook/task-attempts/pi-vs-pi-fff/pi-baseline/"
                "django__django-11099.json",
                report,
            )
            self.assertIn(
                str(logbook_dir / "native-report" / "pi-plus-fff.json"),
                report,
            )

    def test_benchmark_report_filter_reports_unknown_vessel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "missing-vessel",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "benchmark report vessel filter matched no vessel: missing-vessel",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_report_filter_reports_unknown_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_multi_vessel_logbook(Path(temp_dir))
            write_benchmark_scorecard(logbook_dir)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                        "--task",
                        "missing-task",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "benchmark report task filter matched no task: missing-task",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_report_command_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = _prepared_multi_vessel_logbook(root)
            output_path = root / "reports" / "benchmark.md"
            write_benchmark_scorecard(logbook_dir)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-report",
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
                        "## Benchmark scorecard",
                        "",
                        "- Regatta: pi-fff-comparison",
                        "- Course: swe-bench-lite",
                        "- Status: complete",
                        "- Comparisons: 1",
                        "- Vessels: 2",
                        "- Measured: 2",
                        "- Missing: 0",
                        "- Usage: unavailable (missing task-attempt-scorecard.json)",
                        "",
                        "## Artifacts",
                        "",
                        f"- Logbook: {logbook_dir}",
                        f"- Benchmark scorecard: {logbook_dir / 'benchmark-scorecard.json'}",
                        f"- Task attempt scorecard: {logbook_dir / 'task-attempt-scorecard.json'}",
                        f"- Launch result: {logbook_dir / 'benchmark-launch-result.json'}",
                        "- Grading collection: "
                        f"{logbook_dir / 'benchmark-grading-collection.json'}",
                        "",
                        "| Comparison | Baseline | Challenger | Resolved delta | "
                        "Rate delta | Measured | Missing | Eligible | Preflight |",
                        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
                        "| pi-vs-pi-fff | pi-baseline | pi-plus-fff | +1 | +1.000 | "
                        "2/2 | 0 | 0 | preflight-missing:2 |",
                        "",
                        "## Benchmark outcomes by vessel",
                        "",
                        "| Comparison | Vessel | Status | Submitted | Resolved | Rate | Preflight |",
                        "| --- | --- | --- | ---: | ---: | ---: | --- |",
                        "| pi-vs-pi-fff | pi-baseline | measured | 1 | 0 | 0.000 | "
                        "preflight-missing |",
                        "| pi-vs-pi-fff | pi-plus-fff | measured | 1 | 1 | 1.000 | "
                        "preflight-missing |",
                        "",
                    ]
                ),
            )

    def test_benchmark_report_command_reports_missing_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark scorecard artifact "
                "not found:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_report_command_reports_invalid_scorecard_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "benchmark-scorecard.json").write_text(
                "{not json",
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark scorecard artifact "
                "is not valid JSON:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_report_command_reports_invalid_scorecard_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "benchmark-scorecard.json").write_text(
                json.dumps({"schema": "yacht.benchmark-scorecard.v1"}),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "benchmark-report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: benchmark scorecard artifact "
                "is invalid:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

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


def _comparison_delta(
    *,
    resolved_instances_delta: int,
    resolution_rate_delta: float,
) -> dict[str, object]:
    return {
        "baseline_vessel": "pi-baseline",
        "challenger_vessel": "pi-plus-fff",
        "resolved_instances_delta": resolved_instances_delta,
        "resolution_rate_delta": resolution_rate_delta,
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


def _write_task_attempt_scorecard(logbook_dir: Path) -> None:
    (logbook_dir / "task-attempt-scorecard.json").write_text(
        json.dumps(
            {
                "schema": "yacht.task-attempt-scorecard.v1",
                "regatta": "pi-fff-comparison",
                "course": "swe-bench-lite",
                "status": "complete",
                "summary": {
                    "total_comparisons": 1,
                    "total_vessels": 2,
                    "total_attempts": 2,
                    "completed_attempts": 2,
                    "failed_attempts": 0,
                    "total_tool_calls": 7,
                    "tool_call_counts": {
                        "bash": 2,
                        "edit": 2,
                        "fffind": 1,
                        "read": 2,
                    },
                    "total_tokens": 15643,
                    "total_cost": 0.010336,
                    "total_duration_seconds": 12.5,
                },
                "comparisons": [
                    {
                        "name": "pi-vs-pi-fff",
                        "summary": {
                            "total_vessels": 2,
                            "total_attempts": 2,
                            "completed_attempts": 2,
                            "failed_attempts": 0,
                            "total_tool_calls": 7,
                            "tool_call_counts": {
                                "bash": 2,
                                "edit": 2,
                                "fffind": 1,
                                "read": 2,
                            },
                            "total_tokens": 15643,
                            "total_cost": 0.010336,
                            "total_duration_seconds": 12.5,
                        },
                        "vessels": [
                            _task_attempt_vessel(
                                "pi-baseline",
                                tools={"bash": 1, "edit": 1, "read": 1},
                                tokens=9392,
                                cost=0.005823,
                                duration=7.25,
                            ),
                            _task_attempt_vessel(
                                "pi-plus-fff",
                                tools={
                                    "bash": 1,
                                    "edit": 1,
                                    "fffind": 1,
                                    "read": 1,
                                },
                                tokens=6251,
                                cost=0.004513,
                                duration=5.25,
                            ),
                        ],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_task_attempt_scorecard_with_attempt_artifacts(logbook_dir: Path) -> None:
    _write_task_attempt_scorecard(logbook_dir)
    scorecard_path = logbook_dir / "task-attempt-scorecard.json"
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    for comparison in scorecard["comparisons"]:
        for vessel in comparison["vessels"]:
            artifact_path = (
                logbook_dir
                / "task-attempts"
                / comparison["name"]
                / vessel["name"]
                / "django__django-11099.json"
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(
                json.dumps(
                    _task_attempt_artifact(
                        comparison_name=comparison["name"],
                        vessel_name=vessel["name"],
                        tool_calls=_expanded_tool_calls(vessel["tool_call_counts"]),
                        tokens=vessel["total_tokens"],
                        cost=vessel["total_cost"],
                        duration=vessel["total_duration_seconds"],
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            vessel["artifact_paths"] = [str(artifact_path)]
    scorecard_path.write_text(json.dumps(scorecard) + "\n", encoding="utf-8")


def _task_attempt_vessel(
    name: str,
    *,
    tools: dict[str, int],
    tokens: int,
    cost: float,
    duration: float,
) -> dict[str, object]:
    return {
        "name": name,
        "status": "measured",
        "task_attempts": 1,
        "completed_attempts": 1,
        "failed_attempts": 0,
        "success_rate": 1.0,
        "tool_call_count": sum(tools.values()),
        "tool_call_counts": tools,
        "total_tokens": tokens,
        "total_cost": cost,
        "total_duration_seconds": duration,
        "artifact_paths": [
            f"logbook/task-attempts/pi-vs-pi-fff/{name}/django__django-11099.json"
        ],
    }


def _expanded_tool_calls(tool_counts: dict[str, int]) -> list[str]:
    return [
        tool
        for tool, count in tool_counts.items()
        for _ in range(count)
    ]


def _task_attempt_artifact(
    *,
    comparison_name: str,
    vessel_name: str,
    tool_calls: list[str],
    tokens: int,
    cost: float,
    duration: float,
) -> dict[str, object]:
    return {
        "schema": "yacht.task-attempt.v1",
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "comparison": comparison_name,
        "vessel": vessel_name,
        "model": "haiku",
        "rigging": ["pi-fff"] if vessel_name == "pi-plus-fff" else [],
        "runtime": "pi-container",
        "status": "completed",
        "task": {
            "id": "django__django-11099",
            "title": "Fix a SWE-bench Lite regression",
            "difficulty": 3,
        },
        "runtime_context": {
            "backend": "container",
            "temp_home": "/tmp/yacht/home",
            "workspace_path": "/tmp/yacht/workspace",
            "command_prefix": ["docker", "run"],
            "command": ["pi"],
            "cleanup_paths": ["/tmp/yacht"],
        },
        "prompt": "Return a candidate patch.",
        "agent": {
            "exit_code": 0,
            "response": '{"model_patch": "diff --git a/example.py b/example.py"}',
            "tool_calls": tool_calls,
            "transcript_path": "/tmp/yacht/transcript.json",
            "machine_evidence": {
                "format": "pi-jsonl",
                "cost": {"total": cost},
            },
        },
        "metrics": {
            "tokens": tokens,
            "duration_seconds": duration,
        },
        "secret_refs": [],
    }


def _write_grading_collection(logbook_dir: Path) -> None:
    (logbook_dir / "benchmark-grading-collection.json").write_text(
        json.dumps(
            {
                "schema": "yacht.benchmark-grading-collection.v1",
                "regatta": "pi-fff-comparison",
                "course": "swe-bench-lite",
                "adapter": {
                    "kind": "swe-bench",
                    "dataset": "princeton-nlp/SWE-bench_Lite",
                    "split": "test",
                    "harness": "docker",
                },
                "status": "complete",
                "summary": {
                    "total_vessels": 2,
                    "completed_launches": 2,
                    "collected_reports": 2,
                    "missing_native_reports": 0,
                    "invalid_native_reports": 0,
                    "skipped_vessels": 0,
                },
                "comparisons": [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "status": "complete",
                        "vessels": [
                            _grading_collection_vessel(logbook_dir, "pi-baseline"),
                            _grading_collection_vessel(logbook_dir, "pi-plus-fff"),
                        ],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _grading_collection_vessel(
    logbook_dir: Path,
    vessel_name: str,
) -> dict[str, object]:
    return {
        "name": vessel_name,
        "launch_status": "completed",
        "status": "collected",
        "native_report_path": str(
            logbook_dir / "native-report" / f"{vessel_name}.json"
        ),
        "grading_report_path": str(
            logbook_dir
            / "course-handoff"
            / "swe-bench"
            / "vessels"
            / vessel_name
            / "grading-report.json"
        ),
        "submitted_instances": 1,
        "resolved_instances": 1 if vessel_name == "pi-plus-fff" else 0,
        "resolution_rate": 1.0 if vessel_name == "pi-plus-fff" else 0.0,
    }


if __name__ == "__main__":
    unittest.main()
