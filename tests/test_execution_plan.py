"""Task [execution] declarations normalize or fail before any tokens."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yacht._execution_contract import (
    ExecutionContractError,
    validate_execution_plan,
    validate_execution_summary,
)
from yacht.courses.execution import render_execution_plan
from yacht.domain.model import ConfigError

_CAPTURE_MAX = 16 * 1024 * 1024
_CAPTURE_TOTAL_MAX = 64 * 1024 * 1024


def _write_task(
    root: Path,
    *,
    execution: str | None = None,
    episodes: str | None = None,
) -> Path:
    task_dir = root / "budget-task"
    task_dir.mkdir()
    body = '[metadata]\nauthor = "t"\n'
    if episodes is not None:
        body += episodes
        if not body.endswith("\n"):
            body += "\n"
    if execution is not None:
        body += execution
        if not body.endswith("\n"):
            body += "\n"
    (task_dir / "task.toml").write_text(body, encoding="utf-8")
    (task_dir / "instruction.md").write_text("Do the work.\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    return task_dir


def _single_table() -> str:
    return (
        "[execution]\n"
        'mode = "single"\n'
        "max_turns = 30\n"
        "message_timeout_seconds = 900\n"
        "timeout_seconds = 900\n"
    )


def _retained_table() -> str:
    return (
        "[execution]\n"
        'mode = "retained"\n'
        "max_turns = 30\n"
        "message_timeout_seconds = 600\n"
        "timeout_seconds = 7200\n"
        "\n"
        "[[execution.turns]]\n"
        'id = "Q"\n'
        'instruction = "The next scripted user message."\n'
        "\n"
        "[[execution.captures]]\n"
        'after = "Q"\n'
        'path = "plans/retention-answers.json"\n'
        "max_bytes = 1048576\n"
    )


class RenderExecutionPlanTests(unittest.TestCase):
    def test_task_without_execution_table_is_uncapped_single_shot(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp))
            self.assertIsNone(render_execution_plan(task_dir))

    def test_episodes_max_one_is_still_not_an_execution_cap(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes="[episodes]\nmax = 1\n")
            self.assertIsNone(render_execution_plan(task_dir))

    def test_single_shot_plan_keeps_positive_limits(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), execution=_single_table())
            plan = render_execution_plan(task_dir)

        self.assertEqual(plan["mode"], "single")
        self.assertEqual(plan["max_turns"], 30)
        self.assertEqual(plan["message_timeout_seconds"], 900)
        self.assertEqual(plan["timeout_seconds"], 900)
        self.assertNotIn("turns", plan)
        self.assertNotIn("captures", plan)
        self.assertNotIn("initial_turn_id", plan)

    def test_retained_plan_keeps_stable_ids_and_capture_identity(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), execution=_retained_table())
            plan = render_execution_plan(task_dir)

        self.assertEqual(plan["mode"], "retained")
        self.assertEqual(plan["initial_turn_id"], "initial")
        self.assertEqual(
            plan["turns"],
            [{"id": "Q", "instruction": "The next scripted user message."}],
        )
        self.assertEqual(
            plan["captures"],
            [
                {
                    "id": "Q-0",
                    "after": "Q",
                    "path": "plans/retention-answers.json",
                    "max_bytes": 1048576,
                }
            ],
        )

    def test_retained_default_initial_id_is_unique_with_follow_ups(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                execution=(
                    "[execution]\n"
                    'mode = "retained"\n'
                    "max_turns = 2\n"
                    "message_timeout_seconds = 10\n"
                    "timeout_seconds = 20\n"
                    'initial_turn_id = "start"\n'
                    "\n"
                    "[[execution.turns]]\n"
                    'id = "next"\n'
                    'instruction = "Follow up."\n'
                ),
            )
            plan = render_execution_plan(task_dir)

        self.assertEqual(plan["initial_turn_id"], "start")
        self.assertEqual(plan["turns"][0]["id"], "next")

    def test_execution_and_episodes_conflict(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes="[episodes]\nmax = 2\n",
                execution=_single_table(),
            )
            with self.assertRaisesRegex(ConfigError, r"\[execution\].*\[episodes\]"):
                render_execution_plan(task_dir)

    def test_unknown_key_is_an_error(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                execution=_single_table() + "retry = true\n",
            )
            with self.assertRaisesRegex(ConfigError, "unknown"):
                render_execution_plan(task_dir)

    def test_boolean_limits_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                execution=(
                    "[execution]\n"
                    'mode = "single"\n'
                    "max_turns = true\n"
                    "message_timeout_seconds = 900\n"
                    "timeout_seconds = 900\n"
                ),
            )
            with self.assertRaisesRegex(ConfigError, "max_turns"):
                render_execution_plan(task_dir)

    def test_single_mode_rejects_scripted_turns(self) -> None:
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                execution=(
                    _single_table()
                    + "\n[[execution.turns]]\n"
                    + 'id = "Q"\n'
                    + 'instruction = "hidden follow-up"\n'
                ),
            )
            with self.assertRaisesRegex(ConfigError, "single"):
                render_execution_plan(task_dir)


class ValidateExecutionPlanTests(unittest.TestCase):
    def test_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    "mode": "episodes",
                    "max_turns": 1,
                    "message_timeout_seconds": 1,
                    "timeout_seconds": 1,
                }
            )

    def test_rejects_zero_and_negative_limits(self) -> None:
        base = {
            "mode": "single",
            "max_turns": 1,
            "message_timeout_seconds": 1,
            "timeout_seconds": 1,
        }
        for key in ("max_turns", "message_timeout_seconds", "timeout_seconds"):
            with self.subTest(key=key):
                plan = dict(base)
                plan[key] = 0
                with self.assertRaises(ExecutionContractError):
                    validate_execution_plan(plan)

    def test_rejects_bad_ids_and_duplicate_ids(self) -> None:
        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    "mode": "retained",
                    "max_turns": 1,
                    "message_timeout_seconds": 1,
                    "timeout_seconds": 1,
                    "initial_turn_id": "_bad",
                    "turns": [],
                    "captures": [],
                }
            )
        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    "mode": "retained",
                    "max_turns": 1,
                    "message_timeout_seconds": 1,
                    "timeout_seconds": 1,
                    "initial_turn_id": "initial",
                    "turns": [
                        {"id": "initial", "instruction": "clash"},
                    ],
                    "captures": [],
                }
            )

    def test_rejects_unsafe_and_duplicate_capture_paths(self) -> None:
        retained = {
            "mode": "retained",
            "max_turns": 1,
            "message_timeout_seconds": 1,
            "timeout_seconds": 1,
            "initial_turn_id": "initial",
            "turns": [{"id": "Q", "instruction": "next"}],
        }
        for path in (
            "/abs/file.json",
            "../escape.json",
            "foo/./bar.json",
            "foo//bar.json",
            "foo\\bar.json",
            "",
        ):
            with self.subTest(path=path):
                plan = {
                    **retained,
                    "captures": [
                        {
                            "id": "Q-0",
                            "after": "Q",
                            "path": path,
                            "max_bytes": 16,
                        }
                    ],
                }
                with self.assertRaises(ExecutionContractError):
                    validate_execution_plan(plan)

        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    **retained,
                    "captures": [
                        {
                            "id": "Q-0",
                            "after": "Q",
                            "path": "a.json",
                            "max_bytes": 16,
                        },
                        {
                            "id": "Q-1",
                            "after": "Q",
                            "path": "a.json",
                            "max_bytes": 16,
                        },
                    ],
                }
            )

    def test_rejects_capture_over_per_file_and_trial_bounds(self) -> None:
        retained = {
            "mode": "retained",
            "max_turns": 1,
            "message_timeout_seconds": 1,
            "timeout_seconds": 1,
            "initial_turn_id": "initial",
            "turns": [{"id": "Q", "instruction": "next"}],
        }
        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    **retained,
                    "captures": [
                        {
                            "id": "Q-0",
                            "after": "Q",
                            "path": "too-big.json",
                            "max_bytes": _CAPTURE_MAX + 1,
                        }
                    ],
                }
            )
        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    **retained,
                    "captures": [
                        {
                            "id": f"Q-{index}",
                            "after": "Q",
                            "path": f"part-{index}.json",
                            "max_bytes": _CAPTURE_MAX,
                        }
                        for index in range(5)
                    ],
                }
            )
        validate_execution_plan(
            {
                **retained,
                "captures": [
                    {
                        "id": f"Q-{index}",
                        "after": "Q",
                        "path": f"part-{index}.json",
                        "max_bytes": _CAPTURE_TOTAL_MAX // 4,
                    }
                    for index in range(4)
                ],
            }
        )

    def test_capture_after_must_name_a_known_turn(self) -> None:
        with self.assertRaises(ExecutionContractError):
            validate_execution_plan(
                {
                    "mode": "retained",
                    "max_turns": 1,
                    "message_timeout_seconds": 1,
                    "timeout_seconds": 1,
                    "initial_turn_id": "initial",
                    "turns": [{"id": "Q", "instruction": "next"}],
                    "captures": [
                        {
                            "id": "X-0",
                            "after": "X1",
                            "path": "plans/x.json",
                            "max_bytes": 16,
                        }
                    ],
                }
            )


def _summary(**overrides: object) -> dict:
    payload = {
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
                "loops_started": 2,
                "loops_completed": 2,
                "continuation_possible": False,
            }
        ],
        "captures": [],
        "valid": True,
        "model": "test-model",
        "harness": "omp",
        "harness_version": "18.1.17",
        "settings": {
            "compaction.enabled": False,
            "memory.backend": "off",
            "tools": ["bash"],
        },
        "usage": {},
        "cost_usd": None,
        "ended": "cap",
        "handoff": {"verifier": "verifier/yacht-execution"},
    }
    payload.update(overrides)
    return payload


class ValidateExecutionSummaryTests(unittest.TestCase):
    def test_accepts_unknown_cost_and_empty_usage(self) -> None:
        validate_execution_summary(_summary())

    def test_accepts_policy_scalars_and_tool_lists(self) -> None:
        validate_execution_summary(
            _summary(
                settings={
                    "compaction": {"enabled": False, "autoContinue": False},
                    "memory": {"backend": "off"},
                    "tools": ["bash", "read"],
                    "title.refreshOnReplan": False,
                }
            )
        )

    def test_accepts_timeout_with_no_messages(self) -> None:
        validate_execution_summary(
            _summary(
                messages=[],
                session_ids=[],
                ended="timeout",
                valid=False,
            )
        )

    def test_rejects_missing_message_timestamps(self) -> None:
        summary = _summary()
        summary["messages"][0].pop("started_at")
        summary["messages"][0].pop("finished_at")
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(summary)

    def test_rejects_loop_counts_past_the_cap(self) -> None:
        summary = _summary()
        summary["messages"][0]["loops_started"] = 31
        summary["messages"][0]["loops_completed"] = 31
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(summary)

    def test_rejects_completed_loops_ahead_of_started(self) -> None:
        summary = _summary()
        summary["messages"][0]["loops_started"] = 1
        summary["messages"][0]["loops_completed"] = 2
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(summary)

    def test_rejects_capture_after_a_message_that_was_not_delivered(self) -> None:
        summary = _summary(
            captures=[
                {
                    "id": "Q-0",
                    "after": "Q",
                    "path": "plans/x.json",
                    "status": "missing",
                }
            ]
        )
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(summary)

    def test_rejects_message_cost_fabricated_as_boolean(self) -> None:
        summary = _summary()
        summary["messages"][0]["cost_usd"] = True
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(summary)

    def test_rejects_non_finite_cost(self) -> None:
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(_summary(cost_usd=float("nan")))
        with self.assertRaises(ExecutionContractError):
            validate_execution_summary(_summary(cost_usd=float("inf")))


if __name__ == "__main__":
    unittest.main()
