import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yacht.cli import main
from yacht.courses.task_directory import task_directory_digest
from yacht.courses.terminal_bench.harness import harbor_run_config
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.domain.model import load_regatta

FACTORIAL = Path("examples/custom-eval-omp-codex-skill-factorial.toml")


class OmpCodexFactorialCourseTests(unittest.TestCase):
    def test_factorial_holds_task_model_and_within_harness_comparisons(self) -> None:
        regatta = load_regatta(FACTORIAL)

        self.assertEqual(
            {vessel.model for vessel in regatta.vessels},
            {"openai/gpt-5.6-luna"},
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
        skill_targets = [
            ".agents/skills/team-conventions/reference/checklist.md",
            ".agents/skills/team-conventions/templates/tool.py",
            ".agents/skills/team-conventions/SKILL.md",
        ]
        omp_targets = [
            step["target"] for step in jobs["omp-with-skill"]["agent"]["rigging_steps"]
        ]
        codex_targets = [
            step["target"]
            for step in jobs["codex-with-skill"]["agent"]["rigging_steps"]
        ]
        self.assertEqual(omp_targets, skill_targets)
        self.assertEqual(codex_targets, skill_targets)
        for job in jobs.values():
            self.assertEqual(job["secret_env"], ["OPENAI_API_KEY"])
            self.assertEqual(
                harbor_run_config(job, trials_dir=Path("/tmp/trials"))["agents"][0][
                    "env"
                ],
                {"OPENAI_API_KEY": "${OPENAI_API_KEY}"},
            )

    def test_yacht_run_accepts_omp_and_codex_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "yacht.cli.commands.regatta.write_real_benchmark_runbook",
                    return_value={},
                ),
                patch(
                    "yacht.cli.commands.regatta.run_real_benchmark_eval",
                    return_value={
                        "status": "complete",
                        "regatta": "custom-eval-omp-codex-skill-factorial",
                        "course": "team-conventions-ab",
                    },
                ) as eval_mock,
            ):
                exit_code = main(
                    [
                        "run",
                        str(FACTORIAL),
                        "--logbook",
                        temp_dir,
                        "--workspace",
                        temp_dir,
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(eval_mock.call_args.kwargs["agent_name"], "codex, omp")
        self.assertIsNone(eval_mock.call_args.kwargs["agent_prompt_runner_factory"])
        self.assertIsNone(eval_mock.call_args.kwargs["task_agent"])


if __name__ == "__main__":
    unittest.main()
