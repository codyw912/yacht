import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.test_provisioning import PI_FFF_TYPED_INSTALL, PI_WITH_FFF_CONFIG
from yacht.logbook.index import RUN_INDEX_PATH
from yacht.reports.benchmark_status import build_benchmark_status
from yacht.cli import main
from yacht.harnesses.pi import (
    PiAdapter,
    PiPromptRequest,
    PiTaskRequest,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
)
from yacht.preflight import CommandResult
from yacht.workflows.real_benchmark_eval import run_real_benchmark_eval


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

            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ),
                _without_task_workspace_materialization(workspace_path),
            ):
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
                    agent_name="pi",
                    benchmark_command_runner=benchmark_runner,
                )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["agent"], "pi")
            self.assertEqual(
                summary["surfaces"],
                {
                    "agent_harnesses": ["pi"],
                    "benchmark": {
                        "adapter": "swe-bench",
                        "dataset": "princeton-nlp/SWE-bench_Lite",
                        "execution_harness": "docker",
                        "name": "swe-bench-lite",
                        "split": "test",
                    },
                    "tools": ["fff"],
                },
            )
            self.assertEqual(summary["course_handoff"]["status"], "planned")
            self.assertEqual(summary["preflight"]["status"], "passed")
            self.assertEqual(summary["preflight_evidence_report"]["status"], "ready")
            self.assertEqual(summary["attempts"]["status"], "completed")
            self.assertEqual(summary["benchmark_launch"]["status"], "complete")
            self.assertEqual(summary["grading_collection"]["status"], "complete")
            self.assertEqual(summary["scorecard"]["status"], "complete")
            self.assertEqual(
                summary["next_steps"][0]["label"], "Render benchmark report"
            )
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
            self.assertTrue((logbook_dir / RUN_INDEX_PATH).is_file())
            self.assertEqual(
                json.loads(
                    (logbook_dir / "real-benchmark-eval.json").read_text(
                        encoding="utf-8"
                    )
                ),
                summary,
            )
            run_index = json.loads(
                (logbook_dir / RUN_INDEX_PATH).read_text(encoding="utf-8")
            )
            self.assertEqual(run_index["schema"], "yacht.run-index.v1")
            self.assertEqual(run_index["run_kind"], "real-benchmark")
            self.assertEqual(run_index["status"], "complete")
            self.assertEqual(run_index["config_path"], str(config_path))
            self.assertEqual(run_index["logbook"], str(logbook_dir))
            self.assertEqual(run_index["regatta"], "pi-fff-comparison")
            self.assertEqual(run_index["course"], "swe-bench-lite")
            self.assertEqual(
                run_index["comparisons"][0],
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "vessels": ["pi-baseline", "pi-plus-fff"],
                },
            )
            self.assertTrue(run_index["artifacts"]["benchmark_scorecard"]["present"])
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
            preflight_status = next(
                artifact
                for artifact in status["artifacts"]
                if artifact["label"] == "preflight evidence report"
            )
            self.assertEqual(preflight_status["state"], "ready")

    def test_real_benchmark_eval_command_runs_full_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)

            stdout = StringIO()
            stderr = StringIO()
            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiPromptLauncher",
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
                ),
                patch(
                    "yacht.harnesses.registry.SubprocessPiTaskLauncher",
                    return_value=SubprocessPiTaskLauncher(
                        runner=lambda _request: CommandResult(
                            exit_code=0,
                            stdout=json.dumps({"model_patch": MODEL_PATCH}),
                            stderr="",
                        )
                    ),
                ),
                patch(
                    "yacht.workflows.benchmark_launch._run_command",
                    side_effect=_benchmark_command_result,
                ),
                _without_task_workspace_materialization(workspace_path),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
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
            report = stdout.getvalue()
            self.assertIn(
                "Real benchmark eval: pi-fff-comparison / swe-bench-lite",
                report,
            )
            self.assertIn("Status: complete", report)
            self.assertIn(
                "Stages: preflight=ready | attempts=completed | launch=complete | "
                "grading=complete | scorecard=complete",
                report,
            )
            self.assertIn("Benchmark outcomes:", report)
            self.assertIn("Artifacts: logbook=", report)
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

    def test_real_benchmark_eval_command_prints_json_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, workspace_path, logbook_dir = _write_fixture(root)
            stdout = StringIO()

            with (
                patch(
                    "yacht.cli.commands.real_benchmark.run_real_benchmark_eval",
                    return_value={
                        "status": "complete",
                        "regatta": "pi-fff-comparison",
                        "course": "swe-bench-lite",
                        "artifacts": {"logbook": str(logbook_dir)},
                    },
                ),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "real-benchmark-eval",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["artifacts"]["logbook"], str(logbook_dir))

    def test_blocks_with_preflight_guidance_for_unsupported_rigging_capability(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(
                PI_WITH_FFF_CONFIG.replace(
                    'method = "agent-extension"',
                    'method = "package"',
                ),
                encoding="utf-8",
            )
            workspace_path.mkdir()
            adapter = PiAdapter(
                launcher=SubprocessPiPromptLauncher(
                    runner=lambda _request: CommandResult(
                        exit_code=0,
                        stdout='{"available": true, "configured": true}\n',
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
            ):
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
                    agent_name="pi",
                )

            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["preflight"]["status"], "invalid")
            self.assertEqual(
                summary["summary"],
                {
                    "blocked_preflight_vessels": 1,
                    "total_preflight_vessels": 2,
                },
            )
            self.assertEqual(
                summary["blocked_preflight"]["vessels"][0]["reason"],
                "unsupported-rigging-capability",
            )
            self.assertEqual(
                summary["blocked_preflight"]["vessels"][0]["failed_checks"][0],
                {
                    "name": "rigging-capability-pi-fff-package",
                    "kind": "runtime-capability",
                    "status": "failed",
                    "origin": "rigging",
                    "origin_name": "pi-fff",
                    "reason": (
                        "runtime backend host-nix does not support rigging install "
                        "method package yet"
                    ),
                },
            )
            self.assertEqual(
                summary["next_steps"][0]["label"],
                "Inspect preflight evidence",
            )
            self.assertIn(
                "unsupported-rigging-capability",
                summary["next_steps"][0]["reason"],
            )
            self.assertFalse((logbook_dir / "task-attempts").exists())
            status = build_benchmark_status(logbook_dir)
            self.assertEqual(status["status"], "blocked")
            self.assertEqual(
                status["next_steps"][0]["label"],
                "Inspect preflight evidence",
            )
            eval_status = next(
                artifact
                for artifact in status["artifacts"]
                if artifact["label"] == "real benchmark eval"
            )
            self.assertIn(
                "blocked_preflight_vessels=1",
                eval_status["detail"],
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

            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ),
                _without_task_workspace_materialization(workspace_path),
            ):
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
                    agent_name="pi",
                    benchmark_command_runner=lambda _argv, _cwd: CommandResult(
                        exit_code=0,
                        stdout="no report\n",
                        stderr="",
                    ),
                )

            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["agent"], "pi")
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
            self.assertEqual(
                summary["next_steps"][0]["label"], "Rerun benchmark launch"
            )
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

            with (
                patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ),
                _without_task_workspace_materialization(workspace_path),
            ):
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
                    agent_name="pi",
                )

            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["agent"], "pi")
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
            self.assertEqual(status["status"], "blocked")
            self.assertEqual(status["next_steps"][0]["label"], "Inspect task attempts")


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    logbook_dir = root / "logbook"
    config_path.write_text(
        PI_WITH_FFF_CONFIG.replace(
            PI_FFF_TYPED_INSTALL,
            "install = []\n",
        ),
        encoding="utf-8",
    )
    workspace_path.mkdir()
    return config_path, workspace_path, logbook_dir


@contextmanager
def _without_task_workspace_materialization(workspace_path: Path):
    with (
        patch(
            "yacht.courses.registry.SweBenchAdapter.task_with_context",
            autospec=True,
            side_effect=lambda self, *, task, adapter: task,
        ),
        patch(
            "yacht.courses.registry.SweBenchAdapter.workspace_for_attempt",
            autospec=True,
            return_value=workspace_path,
        ),
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
