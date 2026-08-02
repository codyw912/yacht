import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yacht.courses.episodes import DEFAULT_CONTINUE_INSTRUCTION, render_episode_plan
from yacht.domain.model import ConfigError


def _write_task(
    root: Path,
    *,
    episodes_table: str | None,
    deltas: dict[int, str] | None = None,
) -> Path:
    task_dir = root / "relay-task"
    task_dir.mkdir()
    body = '[metadata]\nauthor = "t"\n'
    if episodes_table is not None:
        body += episodes_table
    (task_dir / "task.toml").write_text(body, encoding="utf-8")
    (task_dir / "instruction.md").write_text("episode one\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    for index, text in (deltas or {}).items():
        episodes_dir = task_dir / "episodes"
        episodes_dir.mkdir(exist_ok=True)
        (episodes_dir / f"{index:03d}.md").write_text(text, encoding="utf-8")
    return task_dir


class RenderEpisodePlanTest(unittest.TestCase):
    def test_task_without_episodes_table_is_not_episodic(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table=None)
            self.assertIsNone(render_episode_plan(task_dir))

    def test_max_one_is_inert(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = 1\n")
            self.assertIsNone(render_episode_plan(task_dir))

    def test_full_plan_resolves_deltas_then_continue_instruction(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes_table=(
                    "[episodes]\nmax = 4\nverify_between = true\n"
                    'continue_instruction = "Keep going."\n'
                    "max_turns = 15\ntimeout_seconds = 600\n"
                ),
                deltas={2: "delta two\n", 3: "delta three\n"},
            )
            plan = render_episode_plan(task_dir)
            self.assertEqual(
                plan,
                {
                    "max": 4,
                    "verify_between": True,
                    "instructions": ["delta two\n", "delta three\n", "Keep going."],
                    "max_turns": 15,
                    "timeout_seconds": 600,
                },
            )

    def test_default_continue_instruction(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = 2\n")
            plan = render_episode_plan(task_dir)
            self.assertEqual(plan["instructions"], [DEFAULT_CONTINUE_INSTRUCTION])
            self.assertFalse(plan["verify_between"])

    def test_delta_gap_is_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes_table="[episodes]\nmax = 5\n",
                deltas={2: "two\n", 4: "four\n"},
            )
            with self.assertRaisesRegex(ConfigError, "003"):
                render_episode_plan(task_dir)

    def test_delta_beyond_max_is_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes_table="[episodes]\nmax = 2\n",
                deltas={2: "two\n", 3: "three\n"},
            )
            with self.assertRaisesRegex(ConfigError, "max"):
                render_episode_plan(task_dir)

    def test_deltas_without_table_are_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table=None, deltas={2: "x\n"})
            with self.assertRaisesRegex(ConfigError, r"\[episodes\]"):
                render_episode_plan(task_dir)

    def test_unknown_key_misnamed_delta_and_bad_types_are_errors(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = 2\nbudget = 3\n"
            )
            with self.assertRaisesRegex(ConfigError, "budget"):
                render_episode_plan(task_dir)
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = 3\n")
            episodes_dir = task_dir / "episodes"
            episodes_dir.mkdir(exist_ok=True)
            (episodes_dir / "2.md").write_text("bad name\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "2.md"):
                render_episode_plan(task_dir)
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = true\n")
            with self.assertRaisesRegex(ConfigError, "max"):
                render_episode_plan(task_dir)

    def test_empty_delta_is_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = 2\n", deltas={2: ""}
            )
            with self.assertRaisesRegex(ConfigError, "empty"):
                render_episode_plan(task_dir)

    def test_verify_between_requires_test_script(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = 2\nverify_between = true\n"
            )
            (task_dir / "tests" / "test.sh").unlink()
            with self.assertRaisesRegex(ConfigError, "tests/test.sh"):
                render_episode_plan(task_dir)


if __name__ == "__main__":
    unittest.main()
