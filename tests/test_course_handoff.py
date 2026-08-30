import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.fixtures import REGATTA_CONFIG
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.courses.handoff import load_course_handoff
from yacht.courses.handoff import write_course_handoff
from yacht.domain.model import ConfigError
from yacht.contracts.schemas import (
    COURSE_HANDOFF_SCHEMA,
    SchemaValidationError,
    validate_course_handoff_document,
)


class CourseHandoffTests(unittest.TestCase):
    def test_load_course_handoff_returns_validated_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_course_handoff(Path("examples/pi-fff-provisioning.toml"), logbook_dir)

            handoff = load_course_handoff(logbook_dir)

            self.assertEqual(handoff["schema"], COURSE_HANDOFF_SCHEMA)

    def test_load_course_handoff_rejects_non_planned_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            handoff = write_course_handoff(
                Path("examples/pi-fff-provisioning.toml"),
                logbook_dir,
            )
            handoff["status"] = "complete"
            (logbook_dir / "course-handoff.json").write_text(
                json.dumps(handoff),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "status must be one of"):
                load_course_handoff(logbook_dir)

    def test_load_course_handoff_rejects_malformed_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir(parents=True)
            (logbook_dir / "course-handoff.json").write_text(
                json.dumps({"schema": COURSE_HANDOFF_SCHEMA, "regatta": "demo"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "course handoff"):
                load_course_handoff(logbook_dir)

    def test_load_course_handoff_requires_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            with self.assertRaisesRegex(ConfigError, "not found"):
                load_course_handoff(logbook_dir)

    def test_write_course_handoff_writes_versioned_benchmark_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            handoff = write_course_handoff(config_path, logbook_dir)

            self.assertEqual(handoff["schema"], COURSE_HANDOFF_SCHEMA)
            self.assertEqual(handoff["regatta"], "pi-fff-comparison")
            self.assertEqual(handoff["course"], "swe-bench-lite")
            self.assertEqual(handoff["status"], "planned")
            self.assertEqual(
                handoff["adapter"],
                {
                    "kind": "swe-bench",
                    "dataset": "princeton-nlp/SWE-bench_Lite",
                    "split": "test",
                    "harness": "docker",
                },
            )
            self.assertEqual(
                handoff["tasks"],
                [
                    {
                        "id": "django__django-11099",
                        "title": "Fix a regression",
                        "difficulty": 3,
                    }
                ],
            )
            self.assertEqual(
                handoff["comparisons"],
                [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "vessels": ["pi-baseline", "pi-plus-fff"],
                    }
                ],
            )
            self.assertEqual(
                handoff["expected_outputs"],
                {
                    "candidate_patches": "course-handoff/swe-bench/candidate-patches.jsonl",
                    "grading_report": "course-handoff/swe-bench/grading-report.json",
                },
            )
            self.assertEqual(
                handoff["grading"],
                {
                    "delegated_to": "swe-bench",
                    "execution": "docker-harness",
                    "status": "planned",
                },
            )

            handoff_path = logbook_dir / "course-handoff.json"
            self.assertEqual(
                json.loads(handoff_path.read_text(encoding="utf-8")),
                handoff,
            )

    def test_small_benchmark_example_handoff_lists_all_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            handoff = write_course_handoff(
                Path("examples/container-pi-fff-real-benchmark-small.toml"),
                logbook_dir,
            )

            self.assertEqual(
                [task["id"] for task in handoff["tasks"]],
                ["django__django-11099", "django__django-11179"],
            )
            self.assertEqual(
                handoff["adapter"]["instance_ids"],
                ["django__django-11099", "django__django-11179"],
            )
            self.assertEqual(
                handoff["comparisons"][0]["name"],
                "container-pi-vs-pi-fff-benchmark-small",
            )

    def test_seeded_selection_handoff_records_population_provenance(self) -> None:
        config = """
[regatta]
name = "sampled-benchmark"

[course]
name = "swe-bench-lite"

[course.adapter]
kind = "swe-bench"
dataset = "SWE-bench/SWE-bench_Lite"
split = "test"
harness = "docker"
instance_ids = [
  "django__django-11099",
  "django__django-11179",
  "astropy__astropy-12907",
]
max_instances = 2
selection = { method = "random", seed = 20260823 }

[[vessels]]
name = "baseline"
model = "mock"

[[vessels]]
name = "challenger"
model = "mock"

[[comparisons]]
name = "sampled-comparison"
vessels = ["baseline", "challenger"]
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            handoff = write_course_handoff(config_path, root / "logbook")

        self.assertEqual(
            [task["id"] for task in handoff["tasks"]],
            ["astropy__astropy-12907", "django__django-11099"],
        )
        self.assertEqual(
            handoff["adapter"]["instance_ids"],
            ["astropy__astropy-12907", "django__django-11099"],
        )
        self.assertEqual(
            handoff["adapter"]["instance_selection"],
            {
                "method": "random",
                "algorithm": "sha256-rank-v1",
                "seed": 20260823,
                "requested_instances": 2,
                "population_count": 3,
                "population_digest": (
                    "sha256:bb915f707dc31ccdb6fb6119d8e8c4eb041d1bedd8571b555616a0e3924b8cdb"
                ),
            },
        )
        handoff["adapter"]["instance_selection"]["requested_instances"] = 1
        with self.assertRaisesRegex(
            SchemaValidationError,
            "requested_instances must match the selected task count",
        ):
            validate_course_handoff_document(handoff)

    def test_course_handoff_requires_course_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "course handoff requires course.adapter",
            ):
                write_course_handoff(config_path, logbook_dir)

            self.assertFalse(logbook_dir.exists())

    def test_handoff_command_writes_artifact_and_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "internals",
                        "handoff",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], COURSE_HANDOFF_SCHEMA)
            self.assertEqual(payload["status"], "planned")
            self.assertTrue((logbook_dir / "course-handoff.json").is_file())

    def test_handoff_command_reports_config_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "internals",
                        "handoff",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: course handoff requires course.adapter",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(logbook_dir.exists())


if __name__ == "__main__":
    unittest.main()
