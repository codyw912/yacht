"""Full Harbor job rendering for [execution] caps and unsupported rejection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yacht.courses.terminal_bench.harness import harbor_run_config
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import ConfigError, load_regatta
from yacht.harnesses.omp import OMP_HEADLESS_FLAGS, OmpTaskRequest

CONTROLLED_OMP = "18.1.17"
LEGACY_OMP = "17.2.15"


def _config(*, harness: str, version: str, runtime_name: str | None = None) -> str:
    runtime_name = runtime_name or f"harbor-{harness}"
    return f"""
[regatta]
name = "execution-cap"

[course]
name = "budget-evals"

[[course.tasks]]
id = "budget-task"
title = "Budget task"

[course.adapter]
kind = "custom-eval"
dataset = "evals"
split = "v1"
harness = "harbor"

[runtimes.{runtime_name}]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "{harness}"
harness_version = "{version}"

[[vessels]]
name = "baseline"
model = "test-model"
runtime = "{runtime_name}"

[[vessels]]
name = "candidate"
model = "test-model"
runtime = "{runtime_name}"

[[comparisons]]
name = "baseline-vs-candidate"
course = "budget-evals"
vessels = ["baseline", "candidate"]
"""


def _write_task(
    root: Path,
    *,
    execution: str | None = None,
    episodes: str | None = None,
) -> Path:
    task_dir = root / "evals" / "budget-task"
    task_dir.mkdir(parents=True)
    (task_dir / "instruction.md").write_text("Do the work.\n", encoding="utf-8")
    (task_dir / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    body = (
        '[metadata]\nauthor = "yacht"\ndescription = "Budget."\n'
        'difficulty = "easy"\n\n[verifier]\ntimeout_sec = 60.0\n\n'
        "[agent]\ntimeout_sec = 300.0\n"
    )
    if episodes is not None:
        body += "\n" + episodes
        if not body.endswith("\n"):
            body += "\n"
    if execution is not None:
        body += "\n" + execution
        if not body.endswith("\n"):
            body += "\n"
    (task_dir / "task.toml").write_text(body, encoding="utf-8")
    return task_dir


def _write_inputs(
    root: Path,
    *,
    harness: str,
    version: str,
    execution: str | None = None,
    episodes: str | None = None,
) -> Path:
    _write_task(root, execution=execution, episodes=episodes)
    config_path = root / "regatta.toml"
    config_path.write_text(_config(harness=harness, version=version), encoding="utf-8")
    return config_path


_SINGLE = (
    "[execution]\n"
    'mode = "single"\n'
    "max_turns = 30\n"
    "message_timeout_seconds = 900\n"
    "timeout_seconds = 900\n"
)
_RETAINED = (
    "[execution]\n"
    'mode = "retained"\n'
    "max_turns = 30\n"
    "message_timeout_seconds = 600\n"
    "timeout_seconds = 7200\n"
    "\n"
    "[[execution.turns]]\n"
    'id = "Q"\n'
    'instruction = "Ask the quiz."\n'
    "\n"
    "[[execution.captures]]\n"
    'after = "Q"\n'
    'path = "plans/retention-answers.json"\n'
    "max_bytes = 1048576\n"
)
_EPISODES_CAPPED = "[episodes]\nmax = 3\nmax_turns = 15\ntimeout_seconds = 600\n"
_EPISODES_UNCAPPED = "[episodes]\nmax = 3\ntimeout_seconds = 600\n"


class ExecutionJobRenderingTests(unittest.TestCase):
    def test_renders_single_shot_cap_without_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=CONTROLLED_OMP,
                execution=_SINGLE,
            )
            job = render_terminal_bench_job(
                regatta=load_regatta(config_path),
                vessel_name="baseline",
            )

        self.assertNotIn("episodes", job["agent"])
        plan = job["agent"]["execution"]["budget-task"]
        self.assertEqual(plan["mode"], "single")
        self.assertEqual(plan["max_turns"], 30)
        kwargs = harbor_run_config(job, trials_dir=Path("/tmp/trials"))["agents"][0][
            "kwargs"
        ]
        self.assertEqual(kwargs["execution"]["budget-task"]["max_turns"], 30)

    def test_renders_retained_ids_into_launcher_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=CONTROLLED_OMP,
                execution=_RETAINED,
            )
            job = render_terminal_bench_job(
                regatta=load_regatta(config_path),
                vessel_name="baseline",
            )

        plan = job["agent"]["execution"]["budget-task"]
        self.assertEqual(plan["mode"], "retained")
        self.assertEqual(plan["initial_turn_id"], "initial")
        self.assertEqual(plan["turns"][0]["id"], "Q")
        self.assertEqual(plan["captures"][0]["id"], "Q-0")
        kwargs = harbor_run_config(job, trials_dir=Path("/tmp/trials"))["agents"][0][
            "kwargs"
        ]
        self.assertEqual(
            kwargs["execution"]["budget-task"]["captures"][0]["after"], "Q"
        )

    def test_omits_execution_when_task_does_not_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=CONTROLLED_OMP,
            )
            job = render_terminal_bench_job(
                regatta=load_regatta(config_path),
                vessel_name="baseline",
            )

        self.assertNotIn("execution", job["agent"])
        kwargs = harbor_run_config(job, trials_dir=Path("/tmp/trials"))["agents"][0][
            "kwargs"
        ]
        self.assertNotIn("execution", kwargs)

    def test_rejects_execution_on_old_omp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=LEGACY_OMP,
                execution=_SINGLE,
            )
            with self.assertRaisesRegex(ConfigError, "18\\.1\\.17"):
                render_terminal_bench_job(
                    regatta=load_regatta(config_path),
                    vessel_name="baseline",
                )

    def test_rejects_execution_on_unsupported_harnesses(self) -> None:
        for harness, version in (
            ("claude-code", "2.1.211"),
            ("codex", "0.147.0"),
            ("pi", "0.74.0"),
        ):
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as tmp:
                config_path = _write_inputs(
                    Path(tmp),
                    harness=harness,
                    version=version,
                    execution=_SINGLE,
                )
                with self.assertRaisesRegex(ConfigError, harness):
                    render_terminal_bench_job(
                        regatta=load_regatta(config_path),
                        vessel_name="baseline",
                    )

    def test_pinned_omp_cold_episode_cap_is_version_aware(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=CONTROLLED_OMP,
                episodes=_EPISODES_CAPPED,
            )
            job = render_terminal_bench_job(
                regatta=load_regatta(config_path),
                vessel_name="baseline",
            )

        self.assertEqual(job["agent"]["episodes"]["budget-task"]["max_turns"], 15)
        self.assertNotIn("execution", job["agent"])

    def test_legacy_omp_still_rejects_unenforceable_episode_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=LEGACY_OMP,
                episodes=_EPISODES_CAPPED,
            )
            with self.assertRaisesRegex(
                ConfigError,
                "episodic max_turns is not enforceable on the omp harness",
            ):
                render_terminal_bench_job(
                    regatta=load_regatta(config_path),
                    vessel_name="baseline",
                )

    def test_uncapped_omp_episodes_remain_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="omp",
                version=LEGACY_OMP,
                episodes=_EPISODES_UNCAPPED,
            )
            job = render_terminal_bench_job(
                regatta=load_regatta(config_path),
                vessel_name="baseline",
            )

        self.assertEqual(job["agent"]["episodes"]["budget-task"]["max"], 3)
        self.assertNotIn("max_turns", job["agent"]["episodes"]["budget-task"])
        self.assertNotIn("execution", job["agent"])

    def test_claude_native_episode_cap_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                harness="claude-code",
                version="2.1.211",
                episodes=_EPISODES_CAPPED,
            )
            job = render_terminal_bench_job(
                regatta=load_regatta(config_path),
                vessel_name="baseline",
            )

        self.assertEqual(job["agent"]["episodes"]["budget-task"]["max_turns"], 15)

    def test_host_omp_adapter_has_no_execution_intake(self) -> None:
        self.assertIn("--no-session", OMP_HEADLESS_FLAGS)
        self.assertNotIn("execution", OmpTaskRequest.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
