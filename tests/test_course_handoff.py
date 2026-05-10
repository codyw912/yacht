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
from yacht.course_handoff import write_course_handoff
from yacht.regatta import ConfigError
from yacht.schemas import COURSE_HANDOFF_SCHEMA


class CourseHandoffTests(unittest.TestCase):
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
