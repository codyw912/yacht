import json
import tempfile
import unittest
from pathlib import Path

from tests.fixtures import REGATTA_CONFIG
from yacht.regatta import Metrics, Task, Vessel, Wake, run_regatta


class FixedTaskRunner:
    def run_task(self, regatta: str, course: str, vessel: Vessel, task: Task) -> Wake:
        return Wake(
            regatta=regatta,
            course=course,
            vessel=vessel.name,
            model=vessel.model,
            rigging=vessel.rigging,
            task_id=task.id,
            task_title=task.title,
            passed=task.id == "task-1",
            metrics=Metrics(tokens=42, duration_seconds=1.5),
        )


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
            self.assertEqual(
                wake,
                {
                    "course": "tiny-course",
                    "metrics": {
                        "duration_seconds": 11.5,
                        "tokens": 850,
                    },
                    "model": "mock-fast",
                    "passed": True,
                    "regatta": "memory-smoke-test",
                    "rigging": [],
                    "schema": "yacht.wake.v1",
                    "task_id": "task-1",
                    "task_title": "Fix a failing test",
                    "vessel": "baseline",
                },
            )

            saved_scorecard = json.loads(
                (logbook_dir / "scorecard.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved_scorecard, scorecard)

    def test_run_regatta_can_use_custom_task_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")

            scorecard = run_regatta(config_path, logbook_dir, runner=FixedTaskRunner())

            self.assertEqual(scorecard["vessels"][0]["tasks_passed"], 1)
            self.assertEqual(scorecard["vessels"][0]["success_rate"], 0.5)
            self.assertEqual(scorecard["vessels"][0]["total_tokens"], 84)
            self.assertEqual(scorecard["vessels"][0]["total_duration_seconds"], 3.0)

            wake = json.loads(
                (logbook_dir / "wake" / "baseline__task-2.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(wake["passed"])
            self.assertEqual(wake["metrics"], {"duration_seconds": 1.5, "tokens": 42})


if __name__ == "__main__":
    unittest.main()
