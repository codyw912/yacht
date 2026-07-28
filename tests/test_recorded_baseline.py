import json
import tempfile
import unittest
from pathlib import Path

from yacht.config.loader import load_regatta
from yacht.courses.handoff import build_course_handoff, write_course_handoff
from yacht.courses.swe_bench.grading import write_swe_bench_grading_report
from yacht.courses.swe_bench.predictions import write_swe_bench_predictions
from yacht.domain.model import ConfigError
from yacht.reports.benchmark_scorecard import write_benchmark_scorecard
from yacht.workflows.baseline import (
    load_baseline_record,
    verify_baseline_comparability,
)
from yacht.workflows.real_benchmark_eval import run_real_benchmark_eval


EXAMPLE_CONFIG = Path("examples/pi-fff-provisioning.toml")
LIVE_COMPARISON_VESSELS = 'vessels = ["pi-baseline", "pi-plus-fff"]'

RECORDED_PREDICTIONS = [
    {
        "instance_id": "django__django-11099",
        "model_name_or_path": "pi-baseline",
        "model_patch": (
            "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n"
        ),
    }
]
RECORDED_NATIVE_REPORT = {
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
RECORDED_RUN_DATE = "2026-07-20T10:00:00Z"


class RecordedBaselineConfigTests(unittest.TestCase):
    def test_load_regatta_parses_baseline_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _baseline_config(root, Path("runs/recorded"))

            regatta = load_regatta(config_path)

            comparison = regatta.comparisons[0]
            self.assertEqual(comparison.vessels, ("pi-plus-fff",))
            assert comparison.baseline is not None
            self.assertEqual(comparison.baseline.vessel, "pi-baseline")
            self.assertEqual(
                comparison.baseline.logbook,
                (root / "runs/recorded").resolve(),
            )

    def test_config_requires_exactly_one_live_vessel_with_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _baseline_config(
                root,
                root / "recorded",
                live_vessels='vessels = ["pi-baseline", "pi-plus-fff"]',
            )

            with self.assertRaises(ConfigError) as raised:
                load_regatta(config_path)
            self.assertIn("exactly one live vessel", str(raised.exception))

    def test_config_requires_declared_baseline_vessel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _baseline_config(
                root,
                root / "recorded",
                baseline_vessel="unknown-vessel",
            )

            with self.assertRaises(ConfigError) as raised:
                load_regatta(config_path)
            self.assertIn("undefined vessel unknown-vessel", str(raised.exception))

    def test_config_requires_distinct_baseline_vessel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _baseline_config(
                root,
                root / "recorded",
                baseline_vessel="pi-plus-fff",
            )

            with self.assertRaises(ConfigError) as raised:
                load_regatta(config_path)
            self.assertIn("must differ from the live vessel", str(raised.exception))

    def test_two_vessel_minimum_still_applies_without_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(
                EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
                    LIVE_COMPARISON_VESSELS,
                    'vessels = ["pi-plus-fff"]',
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError) as raised:
                load_regatta(config_path)
            self.assertIn("at least two", str(raised.exception))

    def test_course_handoff_carries_baseline_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = root / "recorded"
            config_path = _baseline_config(root, recorded_logbook)

            handoff = build_course_handoff(config_path)

            self.assertEqual(
                handoff["comparisons"],
                [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "vessels": ["pi-plus-fff"],
                        "baseline": {
                            "logbook": str(recorded_logbook.resolve()),
                            "vessel": "pi-baseline",
                        },
                    }
                ],
            )


class RecordedBaselineVerificationTests(unittest.TestCase):
    def test_verification_passes_for_matching_recorded_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(root)
            config_path = _baseline_config(root, recorded_logbook)
            regatta = load_regatta(config_path)
            comparison = regatta.comparisons[0]
            assert comparison.baseline is not None

            record = load_baseline_record(comparison.baseline)
            verify_baseline_comparability(
                regatta=regatta,
                comparison=comparison,
                current_handoff=build_course_handoff(config_path),
                record=record,
            )

            self.assertEqual(record.run_date, RECORDED_RUN_DATE)
            self.assertTrue(record.grading_report_path.exists())

    def test_verification_names_adapter_and_model_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(
                root,
                provenance_model="claude-haiku",
            )
            config_path = _baseline_config(
                root,
                recorded_logbook,
                mutate=lambda text: text.replace('split = "test"', 'split = "dev"'),
            )
            regatta = load_regatta(config_path)
            comparison = regatta.comparisons[0]
            assert comparison.baseline is not None

            with self.assertRaises(ConfigError) as raised:
                verify_baseline_comparability(
                    regatta=regatta,
                    comparison=comparison,
                    current_handoff=build_course_handoff(config_path),
                    record=load_baseline_record(comparison.baseline),
                )

            message = str(raised.exception)
            self.assertIn("adapter.split: recorded 'test', config 'dev'", message)
            self.assertIn(
                "model.configured: recorded 'claude-haiku', config 'claude-sonnet'",
                message,
            )

    def test_verification_names_harness_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(root)
            config_path = _baseline_config(
                root,
                recorded_logbook,
                mutate=lambda text: text.replace(
                    'harness = "pi"',
                    'harness = "pi"\nharness_version = "2.0.0"',
                ),
            )
            regatta = load_regatta(config_path)
            comparison = regatta.comparisons[0]
            assert comparison.baseline is not None

            with self.assertRaises(ConfigError) as raised:
                verify_baseline_comparability(
                    regatta=regatta,
                    comparison=comparison,
                    current_handoff=build_course_handoff(config_path),
                    record=load_baseline_record(comparison.baseline),
                )

            self.assertIn(
                "harness.version: recorded '1.2.3', config '2.0.0'",
                str(raised.exception),
            )

    def test_verification_names_task_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(root)
            config_path = _baseline_config(
                root,
                recorded_logbook,
                mutate=lambda text: text.replace(
                    'id = "django__django-11099"',
                    'id = "django__django-99999"',
                ),
            )
            regatta = load_regatta(config_path)
            comparison = regatta.comparisons[0]
            assert comparison.baseline is not None

            with self.assertRaises(ConfigError) as raised:
                verify_baseline_comparability(
                    regatta=regatta,
                    comparison=comparison,
                    current_handoff=build_course_handoff(config_path),
                    record=load_baseline_record(comparison.baseline),
                )

            message = str(raised.exception)
            self.assertIn("only in config: django__django-99999", message)
            self.assertIn("only recorded: django__django-11099", message)

    def test_verification_refuses_missing_grading_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(root, with_grading=False)
            config_path = _baseline_config(root, recorded_logbook)
            regatta = load_regatta(config_path)
            comparison = regatta.comparisons[0]
            assert comparison.baseline is not None

            with self.assertRaises(ConfigError) as raised:
                verify_baseline_comparability(
                    regatta=regatta,
                    comparison=comparison,
                    current_handoff=build_course_handoff(config_path),
                    record=load_baseline_record(comparison.baseline),
                )

            self.assertIn("grading report", str(raised.exception))

    def test_verification_refuses_missing_baseline_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _baseline_config(root, root / "never-recorded")
            regatta = load_regatta(config_path)
            comparison = regatta.comparisons[0]
            assert comparison.baseline is not None

            with self.assertRaises(ConfigError) as raised:
                load_baseline_record(comparison.baseline)
            self.assertIn("no course handoff artifact", str(raised.exception))


class RecordedBaselineScorecardTests(unittest.TestCase):
    def test_scorecard_prepends_recorded_vessel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(root)
            config_path = _baseline_config(root, recorded_logbook)
            logbook_dir = root / "logbook"
            write_course_handoff(config_path, logbook_dir)
            write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
            )
            write_swe_bench_grading_report(
                config_path=config_path,
                native_report_path=Path("examples/pi-fff-native-report.json"),
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
            )

            scorecard = write_benchmark_scorecard(logbook_dir)

            self.assertEqual(scorecard["status"], "complete")
            comparison = scorecard["comparisons"][0]
            recorded, live = comparison["vessels"]
            self.assertEqual(recorded["name"], "pi-baseline")
            self.assertEqual(recorded["status"], "recorded")
            self.assertEqual(recorded["resolved_instances"], 1)
            self.assertEqual(recorded["resolved_ids"], ["django__django-11099"])
            self.assertEqual(
                recorded["baseline_source"]["logbook"],
                str(recorded_logbook.resolve()),
            )
            self.assertEqual(
                recorded["baseline_source"]["run_date"],
                RECORDED_RUN_DATE,
            )
            self.assertEqual(
                recorded["baseline_source"]["usage"],
                {
                    "total_tokens": 1200,
                    "total_cost": 0.25,
                    "total_duration_seconds": 30.5,
                    "tool_call_count": 4,
                },
            )
            self.assertEqual(
                recorded["baseline_source"]["provenance"]["model"]["configured"],
                "claude-sonnet",
            )
            self.assertEqual(live["name"], "pi-plus-fff")
            self.assertEqual(live["status"], "measured")
            self.assertEqual(comparison["summary"]["recorded_vessels"], 1)
            self.assertEqual(comparison["summary"]["total_vessels"], 2)
            self.assertEqual(
                comparison["delta"]["baseline_vessel"],
                "pi-baseline",
            )
            self.assertEqual(
                comparison["delta"]["challenger_vessel"],
                "pi-plus-fff",
            )
            self.assertIn("statistics", comparison)
            self.assertEqual(scorecard["summary"]["recorded_vessels"], 1)


class RecordedBaselineEvalTests(unittest.TestCase):
    def test_real_benchmark_eval_blocks_on_baseline_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorded_logbook = _write_baseline_logbook(root)
            config_path = _baseline_config(
                root,
                recorded_logbook,
                mutate=lambda text: text.replace('split = "test"', 'split = "dev"'),
            )
            logbook_dir = root / "logbook"

            summary = run_real_benchmark_eval(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root,
                secret_values={},
                agent_prompt_runner_factory=_unused_factory,
                task_agent=None,
                agent_name="pi",
            )

            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["failed_stage"], "baseline-verification")
            self.assertIn("adapter.split", summary["error"])
            self.assertIn("preflight", summary["skipped"])
            self.assertNotIn("preflight", summary)
            saved = json.loads(
                (logbook_dir / "real-benchmark-eval.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved["status"], "blocked")


def _unused_factory(instance: object, transcript_dir: object) -> object:
    raise AssertionError("preflight must not run when a baseline is not comparable")


def _baseline_config(
    root: Path,
    recorded_logbook: Path,
    *,
    live_vessels: str = 'vessels = ["pi-plus-fff"]',
    baseline_vessel: str = "pi-baseline",
    mutate=None,
) -> Path:
    logbook_value = str(recorded_logbook)
    text = EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
        LIVE_COMPARISON_VESSELS,
        f"{live_vessels}\n"
        f'baseline = {{ logbook = "{logbook_value}", '
        f'vessel = "{baseline_vessel}" }}',
    )
    if mutate is not None:
        text = mutate(text)
    config_path = root / "regatta.toml"
    config_path.write_text(text, encoding="utf-8")
    return config_path


def _write_baseline_logbook(
    root: Path,
    *,
    provenance_model: str = "claude-sonnet",
    with_grading: bool = True,
) -> Path:
    logbook_dir = root / "recorded-logbook"
    write_course_handoff(EXAMPLE_CONFIG, logbook_dir)
    if with_grading:
        predictions_path = root / "recorded-predictions.json"
        native_report_path = root / "recorded-native-report.json"
        predictions_path.write_text(
            json.dumps(RECORDED_PREDICTIONS),
            encoding="utf-8",
        )
        native_report_path.write_text(
            json.dumps(RECORDED_NATIVE_REPORT),
            encoding="utf-8",
        )
        write_swe_bench_predictions(
            config_path=EXAMPLE_CONFIG,
            predictions_path=predictions_path,
            logbook_dir=logbook_dir,
            vessel_name="pi-baseline",
        )
        write_swe_bench_grading_report(
            config_path=EXAMPLE_CONFIG,
            native_report_path=native_report_path,
            logbook_dir=logbook_dir,
            vessel_name="pi-baseline",
        )
    (logbook_dir / "task-attempt-scorecard.json").write_text(
        json.dumps(
            {
                "comparisons": [
                    {
                        "name": "pi-vs-pi-fff",
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "provenance": {
                                    "model": {"configured": provenance_model},
                                    "harness": {"name": "pi", "version": "1.2.3"},
                                },
                                "total_tokens": 1200,
                                "total_cost": 0.25,
                                "total_duration_seconds": 30.5,
                                "tool_call_count": 4,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (logbook_dir / "run-index.json").write_text(
        json.dumps({"updated_at": RECORDED_RUN_DATE}),
        encoding="utf-8",
    )
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
