"""A per-episode turn cap must be enforced or refused, never dropped.

Accepting `max_turns` and ignoring it makes two vessels look like they ran
under the same budget when only one of them did, which is exactly the
claim a comparison is supposed to support.
"""

import tempfile
import unittest
from pathlib import Path

from yacht.courses.episodes import MAX_TURNS_ENFORCING_HARNESSES
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import ConfigError, load_regatta

RUNTIMES = {
    "claude-code": ("harbor-claude", "claude-code", "2.1.211"),
    "omp": ("harbor-omp", "omp", "17.2.15"),
    "codex": ("harbor-codex", "codex", "0.147.0"),
}


def _config(harness: str, *, declared: bool = False, placeholder: bool = True) -> str:
    runtime_name, runtime_harness, version = RUNTIMES[harness]
    declaration = ""
    if declared:
        runtime_name, runtime_harness, version = ("harbor-declared", "acme", "1.0.0")
        cap_flag = ', "--max-turns", "{max_turns}"' if placeholder else ""
        declaration = f"""
[harnesses.acme]
prompt = "argument"
evidence = "stdout"
command = ["acme", "--model", "{{model}}"{cap_flag}]

[harnesses.acme.install]
url = "https://example.invalid/acme-1.0.0"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
"""
    return f"""
[regatta]
name = "episodic-cap"

[course]
name = "relay-evals"

[[course.tasks]]
id = "relay-task"
title = "Relay task"

[course.adapter]
kind = "custom-eval"
dataset = "evals"
split = "v1"
harness = "harbor"
{declaration}
[runtimes.{runtime_name}]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "{runtime_harness}"
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
course = "relay-evals"
vessels = ["baseline", "candidate"]
"""


def _write_inputs(
    root: Path,
    harness: str,
    *,
    cap: bool,
    declared: bool = False,
    placeholder: bool = True,
):
    task_dir = root / "evals" / "relay-task"
    task_dir.mkdir(parents=True)
    (task_dir / "instruction.md").write_text("Episode one.\n", encoding="utf-8")
    (task_dir / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    episodes = "[episodes]\nmax = 3\ntimeout_seconds = 600\n"
    if cap:
        episodes += "max_turns = 15\n"
    (task_dir / "task.toml").write_text(
        '[metadata]\nauthor = "yacht"\ndescription = "Relay."\n'
        'difficulty = "easy"\n\n[verifier]\ntimeout_sec = 60.0\n\n'
        "[agent]\ntimeout_sec = 300.0\n\n" + episodes,
        encoding="utf-8",
    )
    config_path = root / "regatta.toml"
    config_path.write_text(
        _config(harness, declared=declared, placeholder=placeholder),
        encoding="utf-8",
    )
    return config_path


class EpisodicMaxTurnsEnforcementTests(unittest.TestCase):
    def test_rejects_a_cap_omp_and_codex_cannot_enforce(self) -> None:
        for harness in ("omp", "codex"):
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as tmp:
                config_path = _write_inputs(Path(tmp), harness, cap=True)
                regatta = load_regatta(config_path)

                with self.assertRaisesRegex(
                    ConfigError,
                    f"episodic max_turns is not enforceable on the {harness} harness",
                ) as raised:
                    render_terminal_bench_job(regatta=regatta, vessel_name="baseline")

                message = str(raised.exception)
                self.assertIn("relay-task", message)
                self.assertIn("timeout_seconds", message)
                self.assertIn("claude-code", message)

    def test_allows_episodes_without_a_cap_on_omp_and_codex(self) -> None:
        for harness in ("omp", "codex"):
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as tmp:
                config_path = _write_inputs(Path(tmp), harness, cap=False)
                regatta = load_regatta(config_path)

                job = render_terminal_bench_job(regatta=regatta, vessel_name="baseline")

                plan = job["agent"]["episodes"]["relay-task"]
                self.assertEqual(plan["max"], 3)
                self.assertNotIn("max_turns", plan)

    def test_keeps_the_cap_for_a_harness_that_enforces_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(Path(tmp), "claude-code", cap=True)
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(regatta=regatta, vessel_name="baseline")

            self.assertEqual(job["agent"]["episodes"]["relay-task"]["max_turns"], 15)

    def test_keeps_the_cap_for_a_declared_harness_that_opts_in(self) -> None:
        # A declared harness names {max_turns} in its command; the
        # harbor-side runner raises when the placeholder has no cap.
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp), "claude-code", cap=True, declared=True
            )
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(regatta=regatta, vessel_name="baseline")

            self.assertEqual(job["agent"]["episodes"]["relay-task"]["max_turns"], 15)

    def test_rejects_a_cap_a_declared_harness_would_drop(self) -> None:
        # Being declared is not enough. Without {max_turns} in the command
        # the cap is dropped exactly as silently as on OMP.
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                "claude-code",
                cap=True,
                declared=True,
                placeholder=False,
            )
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "episodic max_turns is not enforceable on the acme harness",
            ) as raised:
                render_terminal_bench_job(regatta=regatta, vessel_name="baseline")

            # The remedy for a declared harness is its own placeholder.
            self.assertIn("{max_turns}", str(raised.exception))

    def test_allows_a_declared_harness_without_a_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_inputs(
                Path(tmp),
                "claude-code",
                cap=False,
                declared=True,
                placeholder=False,
            )
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(regatta=regatta, vessel_name="baseline")

            self.assertNotIn("max_turns", job["agent"]["episodes"]["relay-task"])

    def test_claude_code_is_the_enforcing_harness_on_record(self) -> None:
        self.assertEqual(MAX_TURNS_ENFORCING_HARNESSES, frozenset({"claude-code"}))


if __name__ == "__main__":
    unittest.main()
