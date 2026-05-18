import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.benchmark_status import build_benchmark_status
from yacht.cli import main
from yacht.pi_adapter import (
    PiAdapter,
    PiPromptRequest,
    PiTaskRequest,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
)
from yacht.preflight import CommandResult
from yacht.real_benchmark_eval import run_real_benchmark_eval


MODEL_PATCH = (
    "diff --git a/example.py b/example.py\n"
    "--- a/example.py\n"
    "+++ b/example.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


class RealBenchmarkEvalTests(unittest.TestCase):
    def test_runs_preflight_attempts_native_launch_collection_and_scorecard(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)
            prompt_requests = []
            task_requests = []
            native_launches = []

            def prompt_runner(request: PiPromptRequest) -> CommandResult:
                prompt_requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout=(
                        '{"available": true, "configured": true, '
                        '"tool_calls": ["fffind"]}\n'
                    ),
                    stderr="",
                )

            def task_runner(request: PiTaskRequest) -> CommandResult:
                task_requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout=json.dumps({"model_patch": MODEL_PATCH}),
                    stderr="",
                )

            def benchmark_runner(argv: list[str], cwd: Path) -> CommandResult:
                native_launches.append((argv, cwd))
                _write_native_report(argv)
                return CommandResult(exit_code=0, stdout="graded\n", stderr="")

            adapter = PiAdapter(
                launcher=SubprocessPiPromptLauncher(runner=prompt_runner),
                task_launcher=SubprocessPiTaskLauncher(runner=task_runner),
            )

            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), _without_task_workspace_materialization(workspace_path):
                summary = run_real_benchmark_eval(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                    agent_prompt_runner_factory=lambda instance, transcript_dir: (
                        adapter.agent_prompt_runner(
                            instance=instance,
                            transcript_dir=transcript_dir,
                        )
                    ),
                    task_agent=adapter,
                    benchmark_command_runner=benchmark_runner,
                )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["course_handoff"]["status"], "planned")
            self.assertEqual(summary["preflight"]["status"], "passed")
            self.assertEqual(summary["preflight_evidence_report"]["status"], "ready")
            self.assertEqual(summary["attempts"]["status"], "completed")
            self.assertEqual(summary["benchmark_launch"]["status"], "complete")
            self.assertEqual(summary["grading_collection"]["status"], "complete")
            self.assertEqual(summary["scorecard"]["status"], "complete")
            self.assertEqual(summary["next_steps"][0]["label"], "Render benchmark report")
            self.assertEqual(len(prompt_requests), 1)
            self.assertEqual(len(task_requests), 2)
            self.assertEqual(len(native_launches), 2)
            self.assertTrue((logbook_dir / "runtime-instances.json").is_file())
            self.assertTrue((logbook_dir / "course-handoff.json").is_file())
            self.assertTrue((logbook_dir / "preflight-evidence-report.json").is_file())
            self.assertEqual(
                summary["artifacts"]["preflight_evidence_report"],
                str(logbook_dir / "preflight-evidence-report.json"),
            )
            self.assertTrue((logbook_dir / "real-benchmark-eval.json").is_file())
            self.assertEqual(
                json.loads(
                    (logbook_dir / "real-benchmark-eval.json").read_text(
                        encoding="utf-8"
                    )
                ),
                summary,
            )
            self.assertTrue((logbook_dir / "benchmark-scorecard.json").is_file())
            self.assertTrue(
                (
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-baseline/grading-report.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-plus-fff/grading-report.json"
                ).is_file()
            )
            status = build_benchmark_status(logbook_dir)
            preflight_status = status["artifacts"][2]
            self.assertEqual(preflight_status["label"], "preflight evidence")
            self.assertEqual(preflight_status["state"], "ready")

    def test_real_benchmark_eval_command_runs_full_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)

            stdout = StringIO()
            stderr = StringIO()
            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), patch(
                "yacht.cli.SubprocessPiPromptLauncher",
                return_value=SubprocessPiPromptLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout=(
                            '{"available": true, "configured": true, '
                            '"tool_calls": ["fffind"]}\n'
                        ),
                        stderr="",
                    )
                ),
            ), patch(
                "yacht.cli.SubprocessPiTaskLauncher",
                return_value=SubprocessPiTaskLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout=json.dumps({"model_patch": MODEL_PATCH}),
                        stderr="",
                    )
                ),
            ), patch(
                "yacht.benchmark_launch._run_command",
                side_effect=_benchmark_command_result,
            ), _without_task_workspace_materialization(workspace_path), redirect_stdout(
                stdout
            ), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "real-benchmark-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--secret",
                        "anthropic=test-secret",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["course_handoff"]["status"], "planned")
            self.assertEqual(payload["preflight_evidence_report"]["status"], "ready")
            self.assertEqual(payload["scorecard"]["status"], "complete")
            progress = stderr.getvalue()
            self.assertIn("yacht: real benchmark eval started:", progress)
            self.assertIn("yacht: preflight: running", progress)
            self.assertIn("yacht: benchmark launch: running native harness", progress)
            self.assertIn("yacht: real benchmark eval complete: complete", progress)
            launcher_handoff = json.loads(
                (logbook_dir / "benchmark-launcher-handoff.json").read_text(
                    encoding="utf-8"
                )
            )
            command = launcher_handoff["comparisons"][0]["vessels"][0]["command"]
            self.assertEqual(
                command[:5],
                ["uv", "run", "--with", "swebench", "python"],
            )

    def test_blocks_when_native_launch_writes_no_grading_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)
            adapter = PiAdapter(
                launcher=SubprocessPiPromptLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout=(
                            '{"available": true, "configured": true, '
                            '"tool_calls": ["fffind"]}\n'
                        ),
                        stderr="",
                    )
                ),
                task_launcher=SubprocessPiTaskLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout=json.dumps({"model_patch": MODEL_PATCH}),
                        stderr="",
                    )
                ),
            )

            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), _without_task_workspace_materialization(workspace_path):
                summary = run_real_benchmark_eval(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                    agent_prompt_runner_factory=lambda instance, transcript_dir: (
                        adapter.agent_prompt_runner(
                            instance=instance,
                            transcript_dir=transcript_dir,
                        )
                    ),
                    task_agent=adapter,
                    benchmark_command_runner=lambda _argv, _cwd: CommandResult(
                        exit_code=0,
                        stdout="no report\n",
                        stderr="",
                    ),
                )

            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["course_handoff"]["status"], "planned")
            self.assertEqual(summary["preflight_evidence_report"]["status"], "ready")
            self.assertEqual(
                summary["grading_collection"]["summary"]["collected_reports"],
                0,
            )
            self.assertEqual(
                summary["skipped"],
                ["benchmark-scorecard"],
            )
            self.assertEqual(summary["next_steps"][0]["label"], "Rerun benchmark launch")
            self.assertFalse((logbook_dir / "benchmark-scorecard.json").exists())

    def test_blocks_when_attempt_response_cannot_become_candidate_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)
            adapter = PiAdapter(
                launcher=SubprocessPiPromptLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout=(
                            '{"available": true, "configured": true, '
                            '"tool_calls": ["fffind"]}\n'
                        ),
                        stderr="",
                    )
                ),
                task_launcher=SubprocessPiTaskLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout="I cannot produce a patch for this task.\n",
                        stderr="",
                    )
                ),
            )

            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ), _without_task_workspace_materialization(workspace_path):
                summary = run_real_benchmark_eval(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                    agent_prompt_runner_factory=lambda instance, transcript_dir: (
                        adapter.agent_prompt_runner(
                            instance=instance,
                            transcript_dir=transcript_dir,
                        )
                    ),
                    task_agent=adapter,
                )

            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["failed_stage"], "predictions-from-attempts")
            self.assertIn(
                "response must be a JSON object with non-empty model_patch",
                summary["error"],
            )
            self.assertEqual(summary["attempts"]["status"], "completed")
            self.assertEqual(summary["task_attempt_scorecard"]["status"], "complete")
            self.assertEqual(summary["predictions"], [])
            self.assertEqual(
                summary["skipped"],
                [
                    "runtime-instances",
                    "benchmark-plan",
                    "benchmark-launcher",
                    "benchmark-launch",
                    "benchmark-collect-grading",
                    "benchmark-scorecard",
                ],
            )
            self.assertEqual(summary["next_steps"][0]["label"], "Inspect task attempts")
            self.assertTrue((logbook_dir / "real-benchmark-eval.json").is_file())
            self.assertFalse((logbook_dir / "runtime-instances.json").exists())
            status = build_benchmark_status(logbook_dir)
            self.assertEqual(status["status"], "partial")
            self.assertEqual(status["next_steps"][0]["label"], "Inspect task attempts")


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    logbook_dir = root / "logbook"
    config_path.write_text(
        PI_WITH_FFF_CONFIG.replace(
            'install = ["npm:@ff-labs/pi-fff"]',
            "install = []",
        ),
        encoding="utf-8",
    )
    workspace_path.mkdir()
    return config_path, workspace_path, logbook_dir


@contextmanager
def _without_task_workspace_materialization(workspace_path: Path):
    with patch(
        "yacht.task_attempt_runner.task_with_swe_bench_context",
        side_effect=lambda *, task, adapter: task,
    ), patch(
        "yacht.task_attempt_runner.materialize_swe_bench_workspace",
        return_value=workspace_path,
    ):
        yield


def _write_native_report(argv: list[str]) -> None:
    report_dir = Path(argv[argv.index("--report_dir") + 1])
    run_id = argv[argv.index("--run_id") + 1]
    vessel_name = run_id.split("__")[-1]
    report_path = report_dir / f"{vessel_name}.{run_id}.json"
    report_path.write_text(
        Path(_native_report_fixture(vessel_name)).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _native_report_fixture(vessel_name: str) -> str:
    if vessel_name == "pi-baseline":
        return "examples/pi-baseline-native-report.json"
    if vessel_name == "pi-plus-fff":
        return "examples/pi-fff-native-report.json"
    raise AssertionError(f"unexpected vessel {vessel_name}")


def _benchmark_command_result(argv: list[str], cwd: Path) -> CommandResult:
    _write_native_report(argv)
    return CommandResult(exit_code=0, stdout=f"graded in {cwd}\n", stderr="")


if __name__ == "__main__":
    unittest.main()
