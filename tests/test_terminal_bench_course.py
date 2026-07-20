import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from yacht.courses.terminal_bench.harness import (
    harbor_command,
    harbor_run_config,
    native_report_from_trials,
    run_terminal_bench_job,
)
from yacht.courses.terminal_bench.job import render_terminal_bench_job
from yacht.courses.terminal_bench.rollout_plan import (
    write_terminal_bench_rollout_plan,
)
from yacht.domain.model import ConfigError, load_regatta
from yacht.preflight import CommandResult
from yacht.workflows.real_benchmark_eval import run_real_benchmark_eval


TERMINAL_BENCH_CONFIG = """
[regatta]
name = "terminal-bench-comparison"

[preflight]
failure_policy = "abort-group"

[course]
name = "terminal-bench-2"

[[course.tasks]]
id = "hello-world"
title = "Print hello world"

[[course.tasks]]
id = "fix-permissions"
title = "Fix file permissions"

[course.adapter]
kind = "terminal-bench"
dataset = "terminal-bench/terminal-bench-2"
split = "2.0"
harness = "harbor"

[runtimes.harbor-claude]
backend = "host-nix"
harness = "claude-code"
harness_version = "2.1.211"
flake = "path:."
command = ["claude"]

[runtimes.harbor-claude.preflight]
required = true
checks = [
  { name = "harbor-available", kind = "command", command = ["harbor", "--version"] },
]

[riggings.fff-mcp]
tools = ["fff"]
instructions = "Use the fff MCP server when searching files."

[riggings.fff-mcp.env]
FFF_MODE = "mcp"

[[riggings.fff-mcp.install]]
method = "mcp-server"
target = "fff"
command = ["mcp-fff", "--stdio"]

[riggings.fff-mcp.preflight]
required = true
checks = [
  { name = "fff-env", kind = "env", env = ["FFF_MODE"] },
]

[[vessels]]
name = "claude-baseline"
model = "claude-haiku-4-5"
runtime = "harbor-claude"

[[vessels]]
name = "claude-with-fff"
model = "claude-haiku-4-5"
runtime = "harbor-claude"
rigging = ["fff-mcp"]

[[comparisons]]
name = "claude-vs-claude-fff"
course = "terminal-bench-2"
vessels = ["claude-baseline", "claude-with-fff"]
"""


def _write_config(root: Path) -> Path:
    config_path = root / "regatta.toml"
    config_path.write_text(TERMINAL_BENCH_CONFIG, encoding="utf-8")
    return config_path


def _trial_result(
    task_name: str,
    *,
    reward: int | float | None = 1,
    exception: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "task_name": task_name,
        "trial_name": f"{task_name}__abc1234",
        "agent_info": {
            "name": "claude-code",
            "version": "2.1.211",
            "model_info": {"name": "claude-haiku-4-5", "provider": "anthropic"},
        },
        "agent_result": {
            "n_input_tokens": 1200,
            "n_cache_tokens": 300,
            "n_output_tokens": 450,
            "cost_usd": 0.0123,
        },
        "started_at": "2026-07-20T10:00:00Z",
        "finished_at": "2026-07-20T10:05:00Z",
    }
    if exception:
        result["exception_info"] = {
            "exception_type": "AgentTimeoutError",
            "exception_message": "agent timed out",
            "exception_traceback": "...",
            "occurred_at": "2026-07-20T10:05:00Z",
        }
    elif reward is not None:
        result["verifier_result"] = {"rewards": {"reward": reward}}
    return result


def _write_trial(trials_dir: Path, result: dict[str, Any]) -> None:
    trial_dir = trials_dir / "harbor" / str(result["trial_name"])
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")


class TerminalBenchJobTests(unittest.TestCase):
    def test_renders_job_with_pinned_agent_and_mcp_rigging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            regatta = load_regatta(_write_config(Path(temp_dir)))

            job = render_terminal_bench_job(
                regatta=regatta,
                vessel_name="claude-with-fff",
            )

        self.assertEqual(job["schema"], "yacht.terminal-bench-job.v1")
        self.assertEqual(
            job["dataset"],
            {"name": "terminal-bench/terminal-bench-2", "version": "2.0"},
        )
        self.assertEqual(job["tasks"], ["hello-world", "fix-permissions"])
        self.assertEqual(job["vessel"], "claude-with-fff")
        self.assertEqual(
            job["agent"],
            {
                "name": "claude-code",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
                "env": {"FFF_MODE": "mcp"},
                "mcp_servers": [
                    {
                        "name": "fff",
                        "command": "mcp-fff",
                        "args": ["--stdio"],
                    }
                ],
            },
        )

    def test_baseline_job_has_no_rigging_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            regatta = load_regatta(_write_config(Path(temp_dir)))

            job = render_terminal_bench_job(
                regatta=regatta,
                vessel_name="claude-baseline",
            )

        self.assertEqual(job["agent"]["env"], {})
        self.assertEqual(job["agent"]["mcp_servers"], [])

    def test_rejects_runtime_without_pinned_harness_version(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace('harness_version = "2.1.211"\n', "")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "runtime harbor-claude must pin harness_version",
            ):
                render_terminal_bench_job(
                    regatta=regatta,
                    vessel_name="claude-baseline",
                )

    def test_rejects_harness_without_harbor_agent(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'harness = "claude-code"', 'harness = "local-smoke"'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "terminal-bench does not support harness local-smoke",
            ):
                render_terminal_bench_job(
                    regatta=regatta,
                    vessel_name="claude-baseline",
                )

    def test_rejects_rigging_install_methods_harbor_cannot_express(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'method = "mcp-server"', 'method = "package"'
        ).replace(
            'command = ["mcp-fff", "--stdio"]',
            'command = ["npm", "install"]\npackage = "npm:@ff-labs/fff@0.3.0"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "install method package is not supported for terminal-bench",
            ):
                render_terminal_bench_job(
                    regatta=regatta,
                    vessel_name="claude-with-fff",
                )


class TerminalBenchRolloutPlanTests(unittest.TestCase):
    def test_writes_roster_and_job_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"

            summary = write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-with-fff",
                comparison_name="claude-vs-claude-fff",
            )

            self.assertEqual(summary["status"], "validated")
            self.assertEqual(
                summary["instance_ids"], ["hello-world", "fix-permissions"]
            )
            roster_path = Path(summary["candidate_patches_path"])
            records = [
                json.loads(line)
                for line in roster_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                records,
                [
                    {
                        "instance_id": "hello-world",
                        "model_name_or_path": "claude-with-fff",
                    },
                    {
                        "instance_id": "fix-permissions",
                        "model_name_or_path": "claude-with-fff",
                    },
                ],
            )
            job = json.loads(
                Path(summary["terminal_bench_job_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(job["vessel"], "claude-with-fff")
            self.assertEqual(job["agent"]["version"], "2.1.211")


class TerminalBenchHarnessTests(unittest.TestCase):
    def test_translates_trials_into_normalized_native_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            _write_trial(trials_dir, _trial_result("hello-world", reward=1))
            _write_trial(trials_dir, _trial_result("fix-permissions", reward=0))
            _write_trial(trials_dir, _trial_result("broken-task", exception=True))
            _write_trial(trials_dir, _trial_result("unscored-task", reward=None))

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=[
                    "hello-world",
                    "fix-permissions",
                    "broken-task",
                    "unscored-task",
                    "never-ran",
                ],
            )

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["total_instances"], 5)
        self.assertEqual(report["submitted_instances"], 5)
        self.assertEqual(report["completed_instances"], 2)
        self.assertEqual(report["resolved_instances"], 1)
        self.assertEqual(report["unresolved_instances"], 1)
        self.assertEqual(report["error_instances"], 2)
        self.assertEqual(report["resolved_ids"], ["hello-world"])
        self.assertEqual(report["unresolved_ids"], ["fix-permissions"])
        self.assertEqual(report["error_ids"], ["broken-task", "unscored-task"])
        self.assertEqual(report["incomplete_ids"], ["never-ran"])
        self.assertEqual(report["empty_patch_ids"], [])
        trial = next(
            item for item in report["trials"] if item["task_name"] == "hello-world"
        )
        self.assertEqual(trial["reward"], 1.0)
        self.assertEqual(
            trial["agent"],
            {
                "name": "claude-code",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
            },
        )
        self.assertEqual(
            trial["usage"],
            {
                "input_tokens": 1200,
                "cache_tokens": 300,
                "output_tokens": 450,
                "cost_usd": 0.0123,
            },
        )

    def test_rejects_trials_for_tasks_outside_the_roster(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            _write_trial(trials_dir, _trial_result("surprise-task", reward=1))

            with self.assertRaisesRegex(
                ConfigError, "tasks outside the roster: surprise-task"
            ):
                native_report_from_trials(
                    trials_dir=trials_dir,
                    roster_ids=["hello-world"],
                )

    def test_rejects_multiple_trials_for_one_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            first = _trial_result("hello-world", reward=1)
            second = _trial_result("hello-world", reward=0)
            second["trial_name"] = "hello-world__zzz9999"
            _write_trial(trials_dir, first)
            _write_trial(trials_dir, second)

            with self.assertRaisesRegex(
                ConfigError, "multiple results for task hello-world"
            ):
                native_report_from_trials(
                    trials_dir=trials_dir,
                    roster_ids=["hello-world"],
                )

    def test_runs_job_and_writes_native_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            summary = write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-baseline",
                comparison_name="claude-vs-claude-fff",
            )
            trials_dir = root / "trials"
            report_dir = root / "native-report"
            harbor_commands = []

            def fake_harbor(argv: list[str], cwd: Path) -> int:
                harbor_commands.append((argv, cwd))
                _write_trial(trials_dir, _trial_result("hello-world", reward=1))
                _write_trial(trials_dir, _trial_result("fix-permissions", reward=0))
                return 0

            run_summary = run_terminal_bench_job(
                job_path=Path(summary["terminal_bench_job_path"]),
                roster_path=Path(summary["candidate_patches_path"]),
                trials_dir=trials_dir,
                report_dir=report_dir,
                run_id="run-1",
                vessel_name="claude-baseline",
                command_runner=fake_harbor,
            )

            self.assertEqual(run_summary["status"], "complete")
            self.assertEqual(run_summary["submitted_instances"], 2)
            self.assertEqual(run_summary["resolved_instances"], 1)
            self.assertEqual(len(harbor_commands), 1)
            argv, cwd = harbor_commands[0]
            self.assertEqual(
                argv, harbor_command(trials_dir / "harbor-run-config.json")
            )
            self.assertEqual(argv[:4], ["uv", "run", "--with", "harbor==0.20.0"])
            self.assertEqual(cwd, trials_dir)
            run_config = json.loads(
                (trials_dir / "harbor-run-config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                run_config["datasets"],
                [
                    {
                        "name": "terminal-bench/terminal-bench-2",
                        "version": "2.0",
                        "task_names": ["hello-world", "fix-permissions"],
                    }
                ],
            )
            self.assertEqual(
                run_config["agents"],
                [
                    {
                        "name": "claude-code",
                        "model_name": "claude-haiku-4-5",
                        "kwargs": {"version": "2.1.211"},
                    }
                ],
            )
            report_path = report_dir / "claude-baseline.run-1.json"
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["resolved_ids"], ["hello-world"])

    def test_fails_when_harbor_run_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            summary = write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-baseline",
                comparison_name="claude-vs-claude-fff",
            )

            with self.assertRaisesRegex(
                ConfigError, "harbor run failed with exit code 3"
            ):
                run_terminal_bench_job(
                    job_path=Path(summary["terminal_bench_job_path"]),
                    roster_path=Path(summary["candidate_patches_path"]),
                    trials_dir=root / "trials",
                    report_dir=root / "native-report",
                    run_id="run-1",
                    vessel_name="claude-baseline",
                    command_runner=lambda argv, cwd: 3,
                )

    def test_run_config_includes_rigging_surface(self) -> None:
        job = {
            "schema": "yacht.terminal-bench-job.v1",
            "dataset": {"name": "terminal-bench/terminal-bench-2", "version": "2.0"},
            "tasks": ["hello-world"],
            "vessel": "claude-with-fff",
            "agent": {
                "name": "claude-code",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
                "env": {"FFF_MODE": "mcp"},
                "mcp_servers": [
                    {"name": "fff", "command": "mcp-fff", "args": ["--stdio"]}
                ],
            },
        }

        run_config = harbor_run_config(job, trials_dir=Path("/tmp/trials"))

        self.assertEqual(
            run_config["agents"][0]["env"],
            {"FFF_MODE": "mcp"},
        )
        self.assertEqual(
            run_config["agents"][0]["mcp_servers"],
            [
                {
                    "transport": "stdio",
                    "name": "fff",
                    "command": "mcp-fff",
                    "args": ["--stdio"],
                }
            ],
        )


class TerminalBenchAttemptsFromTrialsTests(unittest.TestCase):
    def test_synthesizes_attempts_for_missing_and_errored_trials(self) -> None:
        from yacht.courses.terminal_bench.attempts_from_trials import (
            write_terminal_bench_attempts_from_trials,
        )
        from yacht.courses.terminal_bench.harness import native_report_from_trials

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            summary = write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-baseline",
                comparison_name="claude-vs-claude-fff",
            )
            trials_dir = root / "trials"
            _write_trial(trials_dir, _trial_result("hello-world", exception=True))
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world", "fix-permissions"],
            )
            handoff = json.loads(
                (logbook_dir / "course-handoff.json").read_text(encoding="utf-8")
            )
            self.assertEqual(handoff["adapter"]["kind"], "terminal-bench")
            with patch(
                "yacht.courses.terminal_bench.attempts_from_trials."
                "native_report_path_from_launcher_handoff",
                return_value=_written_report(root, report),
            ):
                attempt_summary = write_terminal_bench_attempts_from_trials(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    vessel_name="claude-baseline",
                    comparison_name="claude-vs-claude-fff",
                )

            self.assertEqual(attempt_summary["attempt_count"], 2)
            self.assertEqual(attempt_summary["completed_attempts"], 0)
            self.assertEqual(attempt_summary["failed_attempts"], 2)
            errored = json.loads(
                (
                    logbook_dir
                    / "task-attempts/claude-vs-claude-fff/claude-baseline"
                    / "hello-world.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(errored["status"], "failed")
            self.assertEqual(
                errored["agent"]["machine_evidence"]["exception"]["type"],
                "AgentTimeoutError",
            )
            self.assertEqual(errored["provenance"]["harness"]["version"], "2.1.211")
            missing = json.loads(
                (
                    logbook_dir
                    / "task-attempts/claude-vs-claude-fff/claude-baseline"
                    / "fix-permissions.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(missing["status"], "failed")
            self.assertEqual(
                missing["agent"]["machine_evidence"],
                {
                    "format": "terminal-bench-harbor-trial",
                    "status": "trial-missing",
                },
            )
            self.assertIsNone(missing["provenance"]["harness"]["version"])
            self.assertEqual(
                missing["metrics"],
                {
                    "tokens": 0,
                    "duration_seconds": 0.0,
                },
            )
            self.assertEqual(summary["status"], "validated")


def _written_report(root: Path, report: dict[str, Any]) -> Path:
    report_path = root / "native-report" / "claude-baseline.run-1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


class TerminalBenchRealBenchmarkEvalTests(unittest.TestCase):
    def test_runs_native_rollout_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            workspace_path = root / "workspace"
            workspace_path.mkdir()
            logbook_dir = root / "logbook"
            native_launches = []

            rewards_by_vessel = {
                "claude-baseline": {"hello-world": 1, "fix-permissions": 0},
                "claude-with-fff": {"hello-world": 1, "fix-permissions": 1},
            }

            def benchmark_runner(argv: list[str], cwd: Path) -> CommandResult:
                native_launches.append(argv)
                vessel_name = argv[argv.index("--vessel") + 1]
                trials_dir = Path(argv[argv.index("--trials-dir") + 1])

                def fake_harbor(_harbor_argv: list[str], _cwd: Path) -> int:
                    for task, reward in rewards_by_vessel[vessel_name].items():
                        _write_trial(trials_dir, _trial_result(task, reward=reward))
                    return 0

                run_terminal_bench_job(
                    job_path=Path(argv[argv.index("--job") + 1]),
                    roster_path=Path(argv[argv.index("--roster") + 1]),
                    trials_dir=trials_dir,
                    report_dir=Path(argv[argv.index("--report-dir") + 1]),
                    run_id=argv[argv.index("--run-id") + 1],
                    vessel_name=vessel_name,
                    command_runner=fake_harbor,
                )
                return CommandResult(exit_code=0, stdout="rolled out\n", stderr="")

            def unused_prompt_runner(*args, **kwargs):
                raise AssertionError(
                    "agent prompt runner must not be used for native rollout"
                )

            def unused_prompt_runner_factory(instance, transcript_dir):
                return unused_prompt_runner

            with patch(
                "yacht.preflight._run_command",
                return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
            ):
                summary = run_real_benchmark_eval(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={},
                    agent_prompt_runner_factory=unused_prompt_runner_factory,
                    task_agent=None,
                    agent_name="claude-code",
                    benchmark_command_runner=benchmark_runner,
                )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(
                summary["attempts"],
                {
                    "status": "completed",
                    "mode": "native-rollout",
                },
            )
            self.assertEqual(summary["task_attempt_scorecard"]["status"], "complete")
            self.assertEqual(len(summary["native_attempts"]), 2)
            for entry in summary["native_attempts"]:
                self.assertEqual(entry["mode"], "native-rollout")
                self.assertEqual(entry["attempt_count"], 2)
                self.assertEqual(entry["completed_attempts"], 2)
            attempt_path = (
                logbook_dir
                / "task-attempts/claude-vs-claude-fff/claude-with-fff/hello-world.json"
            )
            self.assertTrue(attempt_path.is_file())
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "completed")
            self.assertEqual(
                attempt["provenance"]["harness"],
                {"name": "claude-code", "version": "2.1.211"},
            )
            self.assertEqual(
                attempt["provenance"]["model"],
                {
                    "configured": "claude-haiku-4-5",
                    "resolved": "claude-haiku-4-5",
                },
            )
            self.assertEqual(
                attempt["provenance"]["runtime"],
                {"backend": "harbor", "image": None},
            )
            self.assertEqual(attempt["metrics"]["tokens"], 1650)
            self.assertEqual(attempt["metrics"]["duration_seconds"], 300.0)
            evidence = attempt["agent"]["machine_evidence"]
            self.assertEqual(evidence["format"], "terminal-bench-harbor-trial")
            self.assertEqual(evidence["reward"], 1.0)
            self.assertEqual(evidence["cost"], {"total": 0.0123})
            self.assertEqual(len(native_launches), 2)
            self.assertEqual(
                native_launches[0][:5],
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "yacht.courses.terminal_bench.harness",
                ],
            )
            for vessel_name in ("claude-baseline", "claude-with-fff"):
                grading_path = (
                    logbook_dir
                    / "course-handoff/terminal-bench/vessels"
                    / vessel_name
                    / "grading-report.json"
                )
                self.assertTrue(grading_path.is_file())
                grading = json.loads(grading_path.read_text(encoding="utf-8"))
                self.assertEqual(grading["schema"], "yacht.terminal-bench-grading.v1")
            scorecard = json.loads(
                (logbook_dir / "benchmark-scorecard.json").read_text(encoding="utf-8")
            )
            vessels = {
                vessel["name"]: vessel
                for comparison in scorecard["comparisons"]
                for vessel in comparison["vessels"]
            }
            self.assertEqual(vessels["claude-baseline"]["resolved_instances"], 1)
            self.assertEqual(vessels["claude-with-fff"]["resolved_instances"], 2)


if __name__ == "__main__":
    unittest.main()
