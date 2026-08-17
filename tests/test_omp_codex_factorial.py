import unittest
from pathlib import Path

from yacht.courses.task_directory import task_directory_digest
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import load_regatta

FACTORIAL = Path("examples/custom-eval-omp-codex-skill-factorial.toml")


class OmpCodexFactorialCourseTests(unittest.TestCase):
    def test_factorial_holds_task_model_and_within_harness_comparisons(self) -> None:
        regatta = load_regatta(FACTORIAL)

        self.assertEqual(
            {vessel.model for vessel in regatta.vessels},
            {"openai/gpt-5.2"},
        )
        self.assertEqual(
            [task.id for task in regatta.course.tasks],
            ["convention-task"],
        )
        self.assertEqual(
            [
                (comparison.name, comparison.vessels)
                for comparison in regatta.comparisons
            ],
            [
                ("omp-skill-vs-baseline", ("omp-baseline", "omp-with-skill")),
                ("codex-skill-vs-baseline", ("codex-baseline", "codex-with-skill")),
            ],
        )
        self.assertEqual(regatta.runtime_recipes["harbor-omp"].harness, "omp")
        self.assertEqual(regatta.runtime_recipes["harbor-codex"].harness, "codex")
        self.assertEqual(
            regatta.runtime_recipes["harbor-omp"].harness_version, "17.2.15"
        )
        self.assertEqual(
            regatta.runtime_recipes["harbor-codex"].harness_version, "0.147.0"
        )

    def test_factorial_jobs_share_task_digest_and_render_logical_skill(self) -> None:
        regatta = load_regatta(FACTORIAL)
        expected_digest = task_directory_digest(Path("examples/custom-evals"))
        jobs = {
            vessel: render_terminal_bench_job(regatta=regatta, vessel_name=vessel)
            for vessel in (
                "omp-baseline",
                "omp-with-skill",
                "codex-baseline",
                "codex-with-skill",
            )
        }

        digests = {job["dataset"]["digest"] for job in jobs.values()}
        self.assertEqual(digests, {expected_digest})
        self.assertEqual(
            jobs["omp-baseline"]["agent"]["import_path"],
            "yacht_harbor_agents.agents:YachtOmp",
        )
        self.assertEqual(
            jobs["codex-baseline"]["agent"]["import_path"],
            "yacht_harbor_agents.agents:YachtCodex",
        )
        self.assertEqual(jobs["omp-baseline"]["agent"]["rigging_steps"], [])
        self.assertEqual(jobs["codex-baseline"]["agent"]["rigging_steps"], [])
        skill_step = {
            "method": "config-file",
            "target": ".agents/skills/team-conventions/SKILL.md",
        }
        omp_targets = [
            step["target"] for step in jobs["omp-with-skill"]["agent"]["rigging_steps"]
        ]
        codex_targets = [
            step["target"]
            for step in jobs["codex-with-skill"]["agent"]["rigging_steps"]
        ]
        self.assertEqual(omp_targets, [skill_step["target"]])
        self.assertEqual(codex_targets, [skill_step["target"]])


if __name__ == "__main__":
    unittest.main()
