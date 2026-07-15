import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.domain.model import ConfigError
from yacht.courses.swe_bench.predictions import write_swe_bench_predictions


VALID_PREDICTIONS = [
    {
        "instance_id": "django__django-11099",
        "model_name_or_path": "pi-plus-fff",
        "model_patch": "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n",
    }
]


class SweBenchPredictionTests(unittest.TestCase):
    def test_write_predictions_validates_against_handoff_and_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text(json.dumps(VALID_PREDICTIONS), encoding="utf-8")

            summary = write_swe_bench_predictions(
                config_path=config_path,
                predictions_path=input_path,
                logbook_dir=logbook_dir,
            )

            self.assertEqual(summary["status"], "validated")
            self.assertEqual(summary["adapter"], "swe-bench")
            self.assertEqual(summary["prediction_count"], 1)
            self.assertEqual(summary["instance_ids"], ["django__django-11099"])
            candidate_path = (
                logbook_dir / "course-handoff/swe-bench/candidate-patches.jsonl"
            )
            self.assertEqual(summary["candidate_patches_path"], str(candidate_path))
            self.assertTrue((logbook_dir / "course-handoff.json").is_file())
            self.assertEqual(
                candidate_path.read_text(encoding="utf-8").splitlines(),
                [
                    json.dumps(
                        {
                            "instance_id": "django__django-11099",
                            "model_name_or_path": "pi-plus-fff",
                            "model_patch": "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n",
                        },
                        sort_keys=True,
                    )
                ],
            )

    def test_rejects_prediction_for_task_outside_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text(
                json.dumps(
                    [VALID_PREDICTIONS[0] | {"instance_id": "django__django-99999"}]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError,
                "prediction instance_id django__django-99999 is not in course handoff",
            ):
                write_swe_bench_predictions(
                    config_path=config_path,
                    predictions_path=input_path,
                    logbook_dir=logbook_dir,
                )

            self.assertFalse(
                (
                    logbook_dir / "course-handoff/swe-bench/candidate-patches.jsonl"
                ).exists()
            )
            self.assertFalse((logbook_dir / "course-handoff.json").exists())

    def test_rejects_duplicate_prediction_instance_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text(
                json.dumps([VALID_PREDICTIONS[0], VALID_PREDICTIONS[0]]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError,
                "prediction instance_id django__django-11099 is duplicated",
            ):
                write_swe_bench_predictions(
                    config_path=config_path,
                    predictions_path=input_path,
                    logbook_dir=logbook_dir,
                )
            self.assertFalse(logbook_dir.exists())

    def test_predictions_command_writes_candidate_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text(json.dumps(VALID_PREDICTIONS), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "predictions",
                        str(config_path),
                        "--input",
                        str(input_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "validated")
            self.assertEqual(payload["prediction_count"], 1)
            self.assertTrue(
                (
                    logbook_dir / "course-handoff/swe-bench/candidate-patches.jsonl"
                ).is_file()
            )

    def test_predictions_command_writes_vessel_candidate_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text(json.dumps(VALID_PREDICTIONS), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "predictions",
                        str(config_path),
                        "--input",
                        str(input_path),
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["vessel"], "pi-plus-fff")
            self.assertTrue(
                (
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-plus-fff/candidate-patches.jsonl"
                ).is_file()
            )

    def test_rejects_vessel_prediction_with_different_model_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text(json.dumps(VALID_PREDICTIONS), encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "prediction model_name_or_path must match vessel pi-baseline",
            ):
                write_swe_bench_predictions(
                    config_path=config_path,
                    predictions_path=input_path,
                    logbook_dir=logbook_dir,
                    vessel_name="pi-baseline",
                )

    def test_predictions_command_reports_config_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            input_path = root / "predictions.json"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            input_path.write_text("[]", encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "predictions",
                        str(config_path),
                        "--input",
                        str(input_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: predictions must contain at least one record",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_example_prediction_file_matches_course_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            summary = write_swe_bench_predictions(
                config_path=Path("examples/pi-fff-provisioning.toml"),
                predictions_path=Path("examples/pi-fff-predictions.json"),
                logbook_dir=logbook_dir,
            )

            self.assertEqual(summary["instance_ids"], ["django__django-11099"])


if __name__ == "__main__":
    unittest.main()
