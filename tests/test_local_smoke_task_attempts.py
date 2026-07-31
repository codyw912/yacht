import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.contracts.schemas import TASK_ATTEMPT_SCHEMA


class LocalSmokeTaskAttemptTests(unittest.TestCase):
    def test_cli_runs_local_smoke_task_attempts_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "internals",
                        "task-attempts",
                        "examples/local-agent-preflight-smoke.toml",
                        "--agent",
                        "local-smoke",
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["attempt_count"], 2)
            self.assertEqual(
                [attempt["vessel"] for attempt in summary["attempts"]],
                ["local-baseline", "local-agent-with-tool"],
            )
            baseline_path = (
                logbook_dir
                / "task-attempts"
                / "local-agent-preflight"
                / "local-baseline"
                / "local-smoke-1.json"
            )
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            self.assertEqual(baseline["agent"]["tool_calls"], [])

            artifact_path = (
                logbook_dir
                / "task-attempts"
                / "local-agent-preflight"
                / "local-agent-with-tool"
                / "local-smoke-1.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["schema"], TASK_ATTEMPT_SCHEMA)
            self.assertEqual(artifact["status"], "completed")
            self.assertEqual(artifact["agent"]["tool_calls"], ["local-smoke"])
            self.assertNotIn("LOCAL_TOOL_STATE", json.dumps(artifact))

            transcript_path = Path(artifact["agent"]["transcript_path"])
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            self.assertEqual(transcript["task_id"], "local-smoke-1")
            self.assertEqual(transcript["tool_calls"], ["local-smoke"])
            self.assertTrue(Path(transcript["state_path"]).is_file())

    def test_cli_writes_task_attempt_scorecard_from_local_smoke_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()

            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "internals",
                            "task-attempts",
                            "examples/local-agent-preflight-smoke.toml",
                            "--agent",
                            "local-smoke",
                            "--logbook",
                            str(logbook_dir),
                            "--workspace",
                            str(workspace_dir),
                        ]
                    ),
                    0,
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "internals",
                        "task-attempt-scorecard",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            scorecard = json.loads(stdout.getvalue())
            self.assertEqual(scorecard["schema"], "yacht.task-attempt-scorecard.v1")
            self.assertEqual(scorecard["status"], "complete")
            self.assertEqual(scorecard["summary"]["total_attempts"], 2)
            comparison = scorecard["comparisons"][0]
            self.assertEqual(comparison["name"], "local-agent-preflight")
            vessels = {vessel["name"]: vessel for vessel in comparison["vessels"]}
            baseline = vessels["local-baseline"]
            rigged = vessels["local-agent-with-tool"]
            self.assertEqual(baseline["distinct_tool_uses"], 0)
            self.assertEqual(baseline["attempts_by_tool"], {})
            self.assertEqual(rigged["distinct_tool_uses"], 1)
            self.assertEqual(rigged["attempts_by_tool"], {"local-smoke": 1})
            self.assertEqual(
                comparison["summary"]["attempts_by_tool"],
                {"local-smoke": 1},
            )
            self.assertEqual(
                scorecard["summary"]["attempts_by_tool"],
                {"local-smoke": 1},
            )
            self.assertEqual(rigged["success_rate"], 1.0)
            self.assertTrue((logbook_dir / "task-attempt-scorecard.json").is_file())


if __name__ == "__main__":
    unittest.main()
