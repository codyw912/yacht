import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.regatta import run_regatta


REGATTA_CONFIG = """
[regatta]
name = "memory-smoke-test"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
  { id = "task-2", title = "Add a CLI flag", difficulty = 2 },
]

[[vessels]]
name = "baseline"
model = "mock-fast"

[[vessels]]
name = "memory-rig"
model = "mock-fast"
rigging = ["memory"]
"""


class RegattaTests(unittest.TestCase):
    def test_run_regatta_writes_wake_and_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")

            scorecard = run_regatta(config_path, logbook_dir)

            self.assertEqual(scorecard["regatta"], "memory-smoke-test")
            self.assertEqual(scorecard["course"], "tiny-course")
            self.assertEqual(
                [vessel["name"] for vessel in scorecard["vessels"]],
                ["baseline", "memory-rig"],
            )
            self.assertEqual(scorecard["vessels"][0]["tasks_passed"], 2)
            self.assertLess(
                scorecard["vessels"][1]["total_tokens"],
                scorecard["vessels"][0]["total_tokens"],
            )

            wake_files = sorted((logbook_dir / "wake").glob("*.json"))
            self.assertEqual(len(wake_files), 4)

            wake = json.loads(wake_files[0].read_text(encoding="utf-8"))
            self.assertEqual(wake["course"], "tiny-course")
            self.assertIn("duration_seconds", wake["metrics"])
            self.assertIn("tokens", wake["metrics"])

            saved_scorecard = json.loads(
                (logbook_dir / "scorecard.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved_scorecard, scorecard)

    def test_cli_run_prints_scorecard_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "run",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((logbook_dir / "scorecard.json").exists())
            self.assertIn('"regatta": "memory-smoke-test"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
