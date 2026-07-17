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

TOP_LEVEL_COMMANDS = {
    "doctor",
    "run",
    "validate",
    "status",
    "report",
    "serve",
    "internals",
}

INTERNAL_COMMANDS = {
    "plan",
    "runtime-instances",
    "handoff",
    "predictions",
    "predictions-from-attempts",
    "grading-report",
    "benchmark-scorecard",
    "benchmark-aggregate",
    "benchmark-plan",
    "benchmark-readiness-report",
    "readiness-gate",
    "benchmark-launcher",
    "benchmark-launch",
    "benchmark-collect-grading",
    "preflight-report",
    "preflight",
    "task-attempts",
    "task-attempt-scorecard",
    "smoke-readiness-report",
}

DISPATCH_CASES = (
    DispatchCase(
        argv=("doctor",),
        patches={
            "commands.doctor.run_doctor": {
                "status": "passed",
                "failed": [],
                "warnings": [],
                "checks": [],
            }
        },
    ),
    DispatchCase(
        argv=("run", CONFIG),
        patches={"commands.regatta.run_regatta": {}},
        extra_patches={
            "commands.regatta.load_regatta": SimpleNamespace(
                course=SimpleNamespace(adapter=None, name="tiny-course"),
                runtime_recipes={},
            )
        },
    ),
    DispatchCase(
        argv=("validate", CONFIG),
        patches={"commands.regatta.load_regatta": SimpleNamespace(name="demo")},
    ),
    DispatchCase(
        argv=("status", "--logbook", "logbook"),
        patches={"commands.inspect.render_benchmark_status": "status\n"},
        extra_patches={"commands.inspect._run_kind": "benchmark"},
    ),
    DispatchCase(
        argv=("report", "--logbook", "logbook"),
        patches={"commands.inspect.render_benchmark_report": "report\n"},
        extra_patches={"commands.inspect._run_kind": "benchmark"},
    ),
    DispatchCase(
        argv=("serve", "--root", "logbooks"),
        patches={"commands.serve.run_server": 0},
    ),
    DispatchCase(
        argv=("internals", "plan", CONFIG),
        patches={"commands.runtimes.build_runtime_plan": {}},
    ),
    DispatchCase(
        argv=("internals", "runtime-instances", CONFIG),
        patches={"commands.runtimes.build_runtime_instances_plan": {}},
    ),
    DispatchCase(
        argv=("internals", "handoff", CONFIG),
        patches={"commands.artifacts.write_course_handoff": {}},
    ),
    DispatchCase(
        argv=("internals", "predictions", CONFIG, "--input", "predictions.json"),
        patches={"commands.artifacts.write_swe_bench_predictions": {}},
    ),
    DispatchCase(
        argv=("internals", "predictions-from-attempts", CONFIG, "--vessel", "baseline"),
        patches={"commands.artifacts.write_swe_bench_predictions_from_attempts": {}},
    ),
    DispatchCase(
        argv=("internals", "grading-report", CONFIG, "--input", "report.json"),
        patches={"commands.artifacts.write_swe_bench_grading_report": {}},
    ),
    DispatchCase(
        argv=("internals", "benchmark-scorecard"),
        patches={"commands.benchmark.write_benchmark_scorecard": {}},
    ),
    DispatchCase(
        argv=("internals", "benchmark-aggregate", "--logbook", "logbook"),
        patches={"commands.benchmark.render_benchmark_aggregate": "aggregate\n"},
    ),
    DispatchCase(
        argv=("internals", "benchmark-plan"),
        patches={"commands.benchmark.write_benchmark_execution_plan": {}},
    ),
    DispatchCase(
        argv=("internals", "benchmark-readiness-report"),
        patches={"commands.benchmark.render_benchmark_readiness_report": "readiness\n"},
    ),
    DispatchCase(
        argv=("internals", "readiness-gate"),
        patches={
            "commands.benchmark.evaluate_readiness_gate": SimpleNamespace(
                summary_json="{}\n",
                blocked_vessel_count=0,
                exit_code=0,
            )
        },
    ),
    DispatchCase(
        argv=("internals", "benchmark-launcher"),
        patches={"commands.benchmark.write_benchmark_launcher_handoff": {}},
    ),
    DispatchCase(
        argv=("internals", "benchmark-launch"),
        patches={
            "commands.benchmark.write_benchmark_launch_result": {"status": "complete"}
        },
    ),
    DispatchCase(
        argv=("internals", "benchmark-collect-grading", CONFIG),
        patches={
            "commands.benchmark.collect_benchmark_grading_reports": {
                "status": "complete"
            }
        },
    ),
    DispatchCase(
        argv=("internals", "preflight-report"),
        patches={"commands.preflight.write_preflight_evidence_report": {}},
        extra_patches={
            "commands.preflight.render_preflight_evidence_report": "report\n"
        },
    ),
    DispatchCase(
        argv=("internals", "preflight", CONFIG),
        patches={"commands.preflight.run_preflight": {"status": "passed"}},
    ),
    DispatchCase(
        argv=("internals", "preflight", CONFIG, "--dry-run"),
        patches={"commands.preflight.build_preflight_execution_plan": {}},
    ),
    DispatchCase(
        argv=("internals", "task-attempts", CONFIG, "--agent", "pi"),
        patches={"commands.attempts.run_task_attempts": {"status": "completed"}},
        extra_patches={"commands.attempts.task_agent": None},
    ),
    DispatchCase(
        argv=("internals", "task-attempt-scorecard"),
        patches={
            "commands.attempts.write_task_attempt_scorecard": {"status": "complete"}
        },
    ),
    DispatchCase(
        argv=("internals", "smoke-readiness-report"),
        patches={"commands.smoke.write_smoke_readiness_report": {"status": "ready"}},
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
                        f"{' '.join(case.argv)} did not call {name} exactly once",
                    )

    def test_top_level_parser_exposes_exactly_the_seven_commands(self) -> None:
        subparsers = self._subparsers_action(build_parser())

        self.assertEqual(set(subparsers.choices), TOP_LEVEL_COMMANDS)

    def test_internals_parser_exposes_exactly_the_stage_commands(self) -> None:
        internals_parser = self._internals_parser()
        internal_subparsers = self._subparsers_action(internals_parser)

        self.assertEqual(set(internal_subparsers.choices), INTERNAL_COMMANDS)

    def test_dispatch_cases_cover_every_registered_command(self) -> None:
        covered_top_level = {case.argv[0] for case in DISPATCH_CASES}
        self.assertEqual(
            covered_top_level,
            TOP_LEVEL_COMMANDS,
            "every top-level CLI command needs a dispatch case in this test",
        )

        covered_internals = {
            case.argv[1] for case in DISPATCH_CASES if case.argv[0] == "internals"
        }
        self.assertEqual(
            covered_internals,
            INTERNAL_COMMANDS,
            "every internals stage command needs a dispatch case in this test",
        )

    def test_unknown_command_is_rejected_by_the_parser(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["not-a-command"])
        self.assertEqual(caught.exception.code, 2)

    def test_unknown_internals_command_is_rejected_by_the_parser(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["internals", "not-a-command"])
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

    def _subparsers_action(
        self, parser: argparse.ArgumentParser
    ) -> argparse._SubParsersAction:
        return next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

    def _internals_parser(self) -> argparse.ArgumentParser:
        subparsers = self._subparsers_action(build_parser())
        return subparsers.choices["internals"]


if __name__ == "__main__":
    unittest.main()
