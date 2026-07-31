"""Writer-to-validator roundtrips for every Harbor-rollout course kind.

The live-run regression behind this module: the custom-eval grading
writer stamps a schema name declared only in the course registry, and a
hand-kept validator list rejected the writer's own artifact mid-run —
caught by a token-spending run, not by the suite. Every registered
grading writer must survive its own validate-on-write at zero token
cost, exercised through the registry the way production reaches it.
The swe-bench and livecodebench writers have roundtrips in their own
course test modules; the registered-schema sync test in test_schemas
covers the vocabulary itself.
"""

import json
import tempfile
import unittest
from pathlib import Path

from yacht.courses.registry import evaluator_adapter
from yacht.courses.terminal_bench.rollout_plan import write_terminal_bench_rollout_plan


HARBOR_ROLLOUT_CASES = (
    {
        "kind": "terminal-bench",
        "config": Path("examples/terminal-bench-claude-code-versions-smoke.toml"),
        "vessel": "claude-code-2-1-211",
        "comparison": "claude-code-211-vs-215",
        "task_id": "fix-git",
        "schema": "yacht.terminal-bench-grading.v1",
    },
    {
        "kind": "aider-polyglot",
        "config": Path("examples/aider-polyglot-claude-code-versions-smoke.toml"),
        "vessel": "claude-code-2-1-211",
        "comparison": "claude-code-211-vs-215-polyglot",
        "task_id": "polyglot_python_wordy",
        "schema": "yacht.aider-polyglot-grading.v1",
    },
    {
        "kind": "custom-eval",
        "config": Path("examples/custom-eval-mcp-ab-smoke.toml"),
        "vessel": "claude-baseline",
        "comparison": "mcp-vs-baseline",
        "task_id": "mcp-task",
        "schema": "yacht.custom-eval-grading.v1",
    },
)


class CourseGradingRoundtripTests(unittest.TestCase):
    def test_every_harbor_grading_writer_survives_its_own_validator(self) -> None:
        for case in HARBOR_ROLLOUT_CASES:
            with self.subTest(kind=case["kind"]):
                self._roundtrip(case)

    def _roundtrip(self, case: dict[str, object]) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            write_terminal_bench_rollout_plan(
                config_path=case["config"],
                logbook_dir=logbook_dir,
                vessel_name=str(case["vessel"]),
                comparison_name=str(case["comparison"]),
            )
            native_report_path = root / "native-report.json"
            native_report_path.write_text(
                json.dumps(_native_report(str(case["task_id"]))),
                encoding="utf-8",
            )

            summary = evaluator_adapter(str(case["kind"])).write_grading_report(
                config_path=case["config"],
                native_report_path=native_report_path,
                logbook_dir=logbook_dir,
                vessel_name=str(case["vessel"]),
            )

            self.assertEqual(summary["status"], "validated")
            artifact = json.loads(
                Path(str(summary["grading_report_path"])).read_text(encoding="utf-8")
            )
            self.assertEqual(artifact["schema"], case["schema"])
            self.assertEqual(artifact["resolved_instances"], 1)


def _native_report(task_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_instances": 1,
        "submitted_instances": 1,
        "completed_instances": 1,
        "resolved_instances": 1,
        "unresolved_instances": 0,
        "empty_patch_instances": 0,
        "error_instances": 0,
        "submitted_ids": [task_id],
        "completed_ids": [task_id],
        "incomplete_ids": [],
        "resolved_ids": [task_id],
        "unresolved_ids": [],
        "empty_patch_ids": [],
        "error_ids": [],
    }


if __name__ == "__main__":
    unittest.main()
