import argparse
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from yacht.cli import build_parser, main


@dataclass(frozen=True)
class DispatchCase:
    argv: tuple[str, ...]
    patches: dict[str, Any]
    exit_code: int = 0
    extra_patches: dict[str, Any] = field(default_factory=dict)


CONFIG = "regatta.toml"

DISPATCH_CASES = (
    DispatchCase(
        argv=("run", CONFIG),
        patches={"commands.regatta.run_regatta": {}},
    ),
    DispatchCase(
        argv=("validate", CONFIG),
        patches={"commands.regatta.load_regatta": SimpleNamespace(name="demo")},
    ),
    DispatchCase(
        argv=("plan", CONFIG),
        patches={"commands.regatta.build_runtime_plan": {}},
    ),
    DispatchCase(
        argv=("runtime-instances", CONFIG),
        patches={"commands.runtimes.build_runtime_instances_plan": {}},
    ),
    DispatchCase(
        argv=("handoff", CONFIG),
        patches={"commands.artifacts.write_course_handoff": {}},
    ),
    DispatchCase(
        argv=("predictions", CONFIG, "--input", "predictions.json"),
        patches={"commands.artifacts.write_swe_bench_predictions": {}},
    ),
    DispatchCase(
        argv=("predictions-from-attempts", CONFIG, "--vessel", "baseline"),
        patches={"commands.artifacts.write_swe_bench_predictions_from_attempts": {}},
    ),
    DispatchCase(
        argv=("grading-report", CONFIG, "--input", "report.json"),
        patches={"commands.artifacts.write_swe_bench_grading_report": {}},
    ),
    DispatchCase(
        argv=("benchmark-scorecard",),
        patches={"commands.benchmark.write_benchmark_scorecard": {}},
    ),
    DispatchCase(
        argv=("benchmark-report",),
        patches={"commands.benchmark.render_benchmark_report": "report\n"},
    ),
    DispatchCase(
        argv=("benchmark-aggregate", "--logbook", "logbook"),
        patches={"commands.benchmark.render_benchmark_aggregate": "aggregate\n"},
    ),
    DispatchCase(
        argv=("benchmark-status",),
        patches={"commands.benchmark.render_benchmark_status": "status\n"},
    ),
    DispatchCase(
        argv=("latest-logbook",),
        patches={"commands.benchmark.render_latest_logbook": "latest\n"},
    ),
    DispatchCase(
        argv=("benchmark-plan",),
        patches={"commands.benchmark.write_benchmark_execution_plan": {}},
    ),
    DispatchCase(
        argv=("benchmark-readiness-report",),
        patches={"commands.benchmark.render_benchmark_readiness_report": "readiness\n"},
    ),
    DispatchCase(
        argv=("readiness-gate",),
        patches={
            "commands.benchmark.evaluate_readiness_gate": SimpleNamespace(
                summary_json="{}\n",
                blocked_vessel_count=0,
                exit_code=0,
            )
        },
    ),
    DispatchCase(
        argv=("benchmark-launcher",),
        patches={"commands.benchmark.write_benchmark_launcher_handoff": {}},
    ),
    DispatchCase(
        argv=("benchmark-launch",),
        patches={
            "commands.benchmark.write_benchmark_launch_result": {"status": "complete"}
        },
    ),
    DispatchCase(
        argv=("benchmark-collect-grading", CONFIG),
        patches={
            "commands.benchmark.collect_benchmark_grading_reports": {
                "status": "complete"
            }
        },
    ),
    DispatchCase(
        argv=("preflight-report",),
        patches={"commands.preflight.write_preflight_evidence_report": {}},
        extra_patches={
            "commands.preflight.render_preflight_evidence_report": "report\n"
        },
    ),
    DispatchCase(
        argv=("smoke-readiness-report",),
        patches={"commands.smoke.write_smoke_readiness_report": {"status": "ready"}},
    ),
    DispatchCase(
        argv=("smoke-report",),
        patches={"commands.smoke.render_smoke_report": "smoke\n"},
    ),
    DispatchCase(
        argv=("preflight", CONFIG),
        patches={"commands.preflight.run_preflight": {"status": "passed"}},
    ),
    DispatchCase(
        argv=("preflight", CONFIG, "--dry-run"),
        patches={"commands.preflight.build_preflight_execution_plan": {}},
    ),
    DispatchCase(
        argv=("task-attempts", CONFIG, "--agent", "pi"),
        patches={"commands.attempts.run_task_attempts": {"status": "completed"}},
        extra_patches={"commands.attempts.task_agent": None},
    ),
    DispatchCase(
        argv=("task-attempt-scorecard",),
        patches={
            "commands.attempts.write_task_attempt_scorecard": {"status": "complete"}
        },
    ),
    DispatchCase(
        argv=("local-smoke-eval", CONFIG),
        patches={"commands.smoke.run_local_smoke_eval": {"status": "complete"}},
    ),
    DispatchCase(
        argv=("pi-smoke-eval", CONFIG),
        patches={"commands.smoke.run_pi_smoke_eval": {"status": "complete"}},
        extra_patches={"commands.smoke.task_agent": None},
    ),
    DispatchCase(
        argv=("real-smoke-eval", CONFIG),
        patches={"commands.smoke.run_real_smoke_eval": {"status": "ready"}},
        extra_patches={
            "commands.smoke.configured_harness_name": "pi",
            "commands.smoke.agent_prompt_runner_factory": None,
            "commands.smoke.task_agent": None,
        },
    ),
    DispatchCase(
        argv=("real-benchmark-eval", CONFIG, "--format", "json"),
        patches={
            "commands.real_benchmark.run_real_benchmark_eval": {"status": "complete"}
        },
        extra_patches={
            "commands.real_benchmark.configured_harness_name": "pi",
            "commands.real_benchmark.agent_prompt_runner_factory": None,
            "commands.real_benchmark.task_agent": None,
        },
    ),
    DispatchCase(
        argv=(
            "real-benchmark-repetitions",
            CONFIG,
            "--repetitions",
            "2",
            "--logbook",
            "logbook",
            "--format",
            "json",
        ),
        patches={
            "commands.real_benchmark.run_real_benchmark_repetitions": {
                "status": "complete"
            }
        },
        extra_patches={
            "commands.real_benchmark.configured_harness_name": "pi",
            "commands.real_benchmark.agent_prompt_runner_factory": None,
            "commands.real_benchmark.task_agent": None,
        },
    ),
    DispatchCase(
        argv=("real-smoke-runbook", CONFIG),
        patches={"commands.smoke.write_real_smoke_runbook": {}},
    ),
    DispatchCase(
        argv=("real-benchmark-runbook", CONFIG),
        patches={"commands.real_benchmark.write_real_benchmark_runbook": {}},
    ),
)


class CliDispatchTests(unittest.TestCase):
    def test_every_command_dispatches_to_its_workflow(self) -> None:
        for case in DISPATCH_CASES:
            with self.subTest(argv=" ".join(case.argv)):
                exit_code, mocks = self._run_case(case)

                self.assertEqual(exit_code, case.exit_code)
                for name in case.patches:
                    self.assertEqual(
                        mocks[name].call_count,
                        1,
                        f"{case.argv[0]} did not call {name} exactly once",
                    )

    def test_dispatch_cases_cover_every_registered_command(self) -> None:
        subparsers = next(
            action
            for action in build_parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        registered = set(subparsers.choices)
        covered = {case.argv[0] for case in DISPATCH_CASES}

        self.assertEqual(
            registered,
            covered,
            "every CLI command needs a dispatch case in this test",
        )

    def test_unknown_command_is_rejected_by_the_parser(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["not-a-command"])
        self.assertEqual(caught.exception.code, 2)

    def _run_case(self, case: DispatchCase) -> tuple[int, dict[str, Any]]:
        mocks: dict[str, Any] = {}
        with ExitStack() as stack:
            for name, value in {**case.patches, **case.extra_patches}.items():
                mocks[name] = stack.enter_context(
                    patch(f"yacht.cli.{name}", return_value=value)
                )
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(list(case.argv))
        return exit_code, mocks


if __name__ == "__main__":
    unittest.main()
