"""Harbor trial execution summaries round-trip into task-attempt evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_task_attempt_document,
)
from yacht.courses.terminal_bench.attempts_from_trials import (
    write_terminal_bench_attempts_from_trials,
)
from yacht.courses.terminal_bench.harness import native_report_from_trials
from yacht.courses.terminal_bench.rollout_plan import write_terminal_bench_rollout_plan
from yacht.domain.model import ConfigError

from tests.test_terminal_bench_course import (
    _trial_result,
    _write_config,
    _write_trial,
    _written_report,
)
from tests.test_execution_rendering import CONTROLLED_OMP, _SINGLE, _write_inputs


def _valid_execution_summary() -> dict[str, Any]:
    return {
        "schema": "yacht.execution.v1",
        "mode": "single",
        "max_turns": 30,
        "message_timeout_seconds": 900,
        "timeout_seconds": 900,
        "session_ids": ["sess-1"],
        "messages": [
            {
                "id": "initial",
                "started_at": "2026-09-11T00:00:00Z",
                "finished_at": "2026-09-11T00:01:00Z",
                "ended": "cap",
                "loops_started": 30,
                "loops_completed": 30,
                "continuation_possible": False,
            }
        ],
        "captures": [
            {
                "id": "initial-0",
                "after": "initial",
                "path": "plans/retention-answers.json",
                "status": "missing",
            }
        ],
        "valid": True,
        "model": "test-model",
        "harness": "omp",
        "harness_version": CONTROLLED_OMP,
        "settings": {
            "compaction": False,
            "title": False,
            "advisor": False,
            "memory": False,
            "autolearn": False,
            "background_jobs": False,
            "auto_model_switching": False,
        },
        "usage": {"input_tokens": 10, "output_tokens": 4},
        "cost_usd": 0.01,
    }


def _write_trial_execution(
    trials_dir: Path,
    trial_name: str,
    summary: dict[str, Any],
) -> None:
    trial_dir = trials_dir / "harbor" / trial_name
    execution_dir = trial_dir / "yacht-execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    (execution_dir / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )


class ExecutionEvidenceRoundTripTests(unittest.TestCase):
    def test_trial_summary_includes_execution_when_present(self) -> None:
        summary = _valid_execution_summary()
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("hello-world", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_execution(trials_dir, trial_name, summary)

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world"],
            )

        trial = report["trials"][0]
        self.assertEqual(trial["execution"], summary)

    def test_trial_summary_omits_execution_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            _write_trial(trials_dir, _trial_result("hello-world", reward=1))
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world"],
            )

        self.assertNotIn("execution", report["trials"][0])

    def test_invalid_execution_summary_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("hello-world", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_execution(
                trials_dir,
                trial_name,
                {"schema": "not-execution", "valid": True},
            )
            with self.assertRaises((ConfigError, SchemaValidationError, ValueError)):
                native_report_from_trials(
                    trials_dir=trials_dir,
                    roster_ids=["hello-world"],
                )

    def test_attempt_machine_evidence_carries_execution_summary(self) -> None:
        summary = _valid_execution_summary()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-baseline",
                comparison_name="claude-vs-claude-fff",
            )
            trials_dir = root / "trials"
            result = _trial_result("hello-world", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_execution(trials_dir, trial_name, summary)
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world", "fix-permissions"],
            )
            with patch(
                "yacht.courses.terminal_bench.attempts_from_trials."
                "native_report_path_from_launcher_handoff",
                return_value=_written_report(root, report),
            ):
                write_terminal_bench_attempts_from_trials(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    vessel_name="claude-baseline",
                    comparison_name="claude-vs-claude-fff",
                )
            attempt = json.loads(
                (
                    logbook_dir
                    / "task-attempts/claude-vs-claude-fff/claude-baseline"
                    / "hello-world.json"
                ).read_text(encoding="utf-8")
            )
            missing = json.loads(
                (
                    logbook_dir
                    / "task-attempts/claude-vs-claude-fff/claude-baseline"
                    / "fix-permissions.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(attempt["agent"]["machine_evidence"]["execution"], summary)
        validate_task_attempt_document(attempt)
        self.assertNotIn("execution", missing["agent"]["machine_evidence"])

    def test_invalid_execution_does_not_count_as_completed(self) -> None:
        summary = _valid_execution_summary()
        summary["valid"] = False
        summary["error"] = "quiescence failed"
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("hello-world", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_execution(trials_dir, trial_name, summary)
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world"],
            )

        self.assertIn("hello-world", report["error_ids"])
        self.assertNotIn("hello-world", report["completed_ids"])
        self.assertEqual(report["trials"][0]["execution"]["valid"], False)

    def test_missing_required_execution_summary_is_infrastructure_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            _write_trial(trials_dir, _trial_result("hello-world", reward=1))
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world"],
                execution_tasks=["hello-world"],
            )

        self.assertIn("hello-world", report["error_ids"])
        self.assertNotIn("hello-world", report["completed_ids"])
        self.assertNotIn("execution", report["trials"][0])

    def test_legacy_trial_without_execution_still_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            _write_trial(trials_dir, _trial_result("hello-world", reward=1))
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world"],
            )

        self.assertIn("hello-world", report["completed_ids"])
        self.assertNotIn("hello-world", report["error_ids"])

    def test_attempt_fails_when_execution_is_invalid_but_keeps_the_summary(
        self,
    ) -> None:
        summary = _valid_execution_summary()
        summary["valid"] = False
        summary["error"] = "capture failed"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-baseline",
                comparison_name="claude-vs-claude-fff",
            )
            trials_dir = root / "trials"
            result = _trial_result("hello-world", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_execution(trials_dir, trial_name, summary)
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world", "fix-permissions"],
            )
            with patch(
                "yacht.courses.terminal_bench.attempts_from_trials."
                "native_report_path_from_launcher_handoff",
                return_value=_written_report(root, report),
            ):
                write_terminal_bench_attempts_from_trials(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    vessel_name="claude-baseline",
                    comparison_name="claude-vs-claude-fff",
                )
            attempt = json.loads(
                (
                    logbook_dir
                    / "task-attempts/claude-vs-claude-fff/claude-baseline"
                    / "hello-world.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(attempt["agent"]["machine_evidence"]["execution"], summary)
        validate_task_attempt_document(attempt)

    def test_attempt_fails_when_controlled_task_has_no_execution_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_inputs(
                root,
                harness="omp",
                version=CONTROLLED_OMP,
                execution=_SINGLE,
            )
            logbook_dir = root / "logbook"
            write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="baseline",
                comparison_name="baseline-vs-candidate",
            )
            trials_dir = root / "trials"
            result = _trial_result("budget-task", reward=1)
            _write_trial(trials_dir, result)
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["budget-task"],
                execution_tasks=["budget-task"],
            )
            with patch(
                "yacht.courses.terminal_bench.attempts_from_trials."
                "native_report_path_from_launcher_handoff",
                return_value=_written_report(root, report),
            ):
                write_terminal_bench_attempts_from_trials(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    vessel_name="baseline",
                    comparison_name="baseline-vs-candidate",
                )
            attempt = json.loads(
                (
                    logbook_dir
                    / "task-attempts/baseline-vs-candidate/baseline"
                    / "budget-task.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(attempt["status"], "failed")
        self.assertNotIn("execution", attempt["agent"]["machine_evidence"])
        self.assertEqual(attempt["metrics"]["tokens"], 1650)


if __name__ == "__main__":
    unittest.main()
