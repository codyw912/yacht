import importlib.util
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
from yacht.courses.registry import native_harness_command


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

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.harbor-claude]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "claude-code"
harness_version = "2.1.211"
required_secrets = ["anthropic"]

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
method = "package"
target = "npm:@ff-labs/mcp-fff@0.3.0"

[[riggings.fff-mcp.install]]
method = "mcp-server"
target = "fff"
command = ["mcp-fff", "--stdio"]

[[riggings.fff-mcp.install]]
method = "config-file"
target = "fff/config.json"
content = '{"mode": "fast"}'

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


def _write_trial_episodes(
    trials_dir: Path,
    trial_name: str,
    episodes: dict[str, Any],
) -> None:
    """Write episodes/summary.json to a trial directory."""
    trial_dir = trials_dir / "harbor" / trial_name
    episodes_dir = trial_dir / "agent" / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    (episodes_dir / "summary.json").write_text(json.dumps(episodes), encoding="utf-8")


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
        self.assertEqual(job["secret_env"], ["ANTHROPIC_API_KEY"])
        self.assertEqual(
            job["agent"],
            {
                "name": "claude-code",
                "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
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
                "rigging_steps": [
                    {
                        "method": "package",
                        "target": "npm:@ff-labs/mcp-fff@0.3.0",
                    },
                    {
                        "method": "config-file",
                        "target": "fff/config.json",
                        "content": '{"mode": "fast"}',
                    },
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
        self.assertEqual(job["agent"]["rigging_steps"], [])

    def test_rejects_runtime_without_pinned_harness_version(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace('harness_version = "2.1.211"\n', "")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "harness_version is required for the harbor backend",
            ):
                load_regatta(config_path)

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
            'method = "mcp-server"', 'method = "preinstalled"'
        ).replace('command = ["mcp-fff", "--stdio"]', "")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "install method preinstalled is not supported for terminal-bench",
            ):
                render_terminal_bench_job(
                    regatta=regatta,
                    vessel_name="claude-with-fff",
                )

    def test_rejects_unpinned_package_rigging(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'target = "npm:@ff-labs/mcp-fff@0.3.0"',
            'target = "npm:@ff-labs/mcp-fff"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "package npm:@ff-labs/mcp-fff must pin a version",
            ):
                render_terminal_bench_job(
                    regatta=regatta,
                    vessel_name="claude-with-fff",
                )

    def test_rejects_agent_extension_targeting_a_different_agent(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'method = "mcp-server"', 'method = "agent-extension"'
        ).replace('command = ["mcp-fff", "--stdio"]', "")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "targets agent None, but runtime harness is claude-code",
            ):
                render_terminal_bench_job(
                    regatta=regatta,
                    vessel_name="claude-with-fff",
                )

    def test_rejects_unpinned_agent_extension_target(self) -> None:
        config = PI_MCP_EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
            'target = "npm:pi-mcp-adapter@2.17.0"',
            'target = "npm:pi-mcp-adapter"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "agent-extension npm:pi-mcp-adapter must pin a version",
            ):
                render_terminal_bench_job(regatta=regatta, vessel_name="pi-with-mcp")

    def test_rejects_agent_extension_target_without_npm_prefix(self) -> None:
        config = PI_MCP_EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
            'target = "npm:pi-mcp-adapter@2.17.0"',
            'target = "pi-mcp-adapter@2.17.0"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "agent-extension pi-mcp-adapter@2.17.0 must use the npm: "
                "prefix for terminal-bench",
            ):
                render_terminal_bench_job(regatta=regatta, vessel_name="pi-with-mcp")


class HarborBackendValidationTests(unittest.TestCase):
    def _expect_invalid(self, config: str, message: str) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, message):
                load_regatta(config_path)

    def test_rejects_command_on_harbor_backend(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'harness = "claude-code"\n',
            'harness = "claude-code"\ncommand = ["claude"]\n',
            1,
        )
        self._expect_invalid(config, "command must not be set for the harbor backend")

    def test_rejects_flake_on_harbor_backend(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'harness = "claude-code"\n',
            'harness = "claude-code"\nflake = "path:."\n',
            1,
        )
        self._expect_invalid(config, "flake must not be set for the harbor backend")

    def test_requires_launcher_image_on_harbor_backend(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'image = "yacht/harbor-launcher:harbor-0.20.0"\n', ""
        )
        self._expect_invalid(config, "image is required for the harbor backend")

    def test_terminal_bench_vessels_must_use_harbor_backend(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            '''backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "claude-code"
harness_version = "2.1.211"''',
            '''backend = "host-nix"
flake = "path:."
command = ["claude"]
harness = "claude-code"
harness_version = "2.1.211"''',
        )
        self._expect_invalid(
            config,
            "must use the harbor backend for the terminal-bench course",
        )

    def test_harbor_backend_requires_a_native_rollout_course(self) -> None:
        config = TERMINAL_BENCH_CONFIG.replace(
            'kind = "terminal-bench"', 'kind = "swe-bench"'
        ).replace('harness = "harbor"', 'harness = "docker"')
        self._expect_invalid(
            config,
            "uses the harbor backend, which requires a native-rollout course",
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
    def test_harbor_command_absolutizes_relative_paths(self) -> None:
        """Docker rejects relative bind mounts ("mount path must be
        absolute"), so a relative --logbook must not reach the -v flags."""
        command = harbor_command(
            Path("relay-logbook/trials/harbor-run-config.json"),
            trials_dir=Path("relay-logbook/trials"),
            secret_env=[],
            tasks_path=Path("examples/custom-evals"),
        )
        trials_abs = Path.cwd() / "relay-logbook" / "trials"
        tasks_abs = Path.cwd() / "examples" / "custom-evals"
        self.assertIn(f"{trials_abs}:{trials_abs}", command)
        self.assertIn(f"{tasks_abs}:{tasks_abs}", command)
        config_arg = command[command.index("-c") + 1]
        self.assertEqual(config_arg, str(trials_abs / "harbor-run-config.json"))

    def test_harbor_run_config_records_absolute_jobs_dir(self) -> None:
        """jobs_dir is read inside the launcher container, where the trials
        dir is mounted at its absolute host path; a relative value would
        strand trial results under /workspace."""
        job = {
            "dataset": {"name": "terminal-bench/terminal-bench-2", "version": "2.0"},
            "tasks": ["hello-world"],
            "agent": {
                "name": "claude-code",
                "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
                "env": {},
                "mcp_servers": [],
                "rigging_steps": [],
            },
        }
        run_config = harbor_run_config(job, trials_dir=Path("relay-logbook/trials"))
        self.assertEqual(
            run_config["jobs_dir"],
            str(Path.cwd() / "relay-logbook" / "trials"),
        )

    def test_harbor_run_config_forwards_secret_env_as_templates(self) -> None:
        job = {
            "dataset": {"name": "terminal-bench/terminal-bench-2", "version": "2.0"},
            "tasks": ["hello-world"],
            "secret_env": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
            "agent": {
                "name": "omp",
                "import_path": "yacht_harbor_agents.agents:YachtOmp",
                "version": "17.2.15",
                "model": "openai/gpt-5.6-luna",
                "env": {"FFF_MODE": "mcp"},
                "mcp_servers": [],
                "rigging_steps": [],
            },
        }

        run_config = harbor_run_config(job, trials_dir=Path("/tmp/trials"))

        self.assertEqual(
            run_config["agents"][0]["env"],
            {
                "FFF_MODE": "mcp",
                "OPENAI_API_KEY": "${OPENAI_API_KEY}",
                "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
            },
        )

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

    def test_trial_summary_includes_episodes_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("relay-task", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            episodes_data = {
                "count": 2,
                "items": [
                    {
                        "index": 1,
                        "ended": "cap",
                        "started_at": "2026-08-01T10:00:00Z",
                        "finished_at": "2026-08-01T10:01:00Z",
                        "usage": {
                            "input_tokens": 500,
                            "output_tokens": 200,
                        },
                        "cost_usd": 0.015,
                    },
                    {
                        "index": 2,
                        "ended": "natural",
                        "started_at": "2026-08-01T10:01:00Z",
                        "finished_at": "2026-08-01T10:02:00Z",
                        "usage": {
                            "input_tokens": 400,
                            "output_tokens": 150,
                        },
                        "cost_usd": 0.012,
                        "reward": 1.0,
                    },
                ],
                "to_resolution": 2,
            }
            _write_trial_episodes(trials_dir, trial_name, episodes_data)

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["relay-task"],
            )

            trial = report["trials"][0]
            self.assertEqual(trial["task_name"], "relay-task")
            self.assertIn("episodes", trial)
            self.assertEqual(trial["episodes"]["count"], 2)
            self.assertEqual(len(trial["episodes"]["items"]), 2)
            self.assertEqual(trial["episodes"]["to_resolution"], 2)
            self.assertEqual(trial["episodes"]["items"][0]["index"], 1)
            self.assertEqual(trial["episodes"]["items"][1]["reward"], 1.0)

    def test_trial_summary_omits_episodes_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            _write_trial(trials_dir, _trial_result("hello-world", reward=1))

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world"],
            )

            trial = report["trials"][0]
            self.assertNotIn("episodes", trial)

    def test_trial_summary_omits_episodes_on_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("relay-task", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            trial_dir = trials_dir / "harbor" / trial_name
            episodes_dir = trial_dir / "agent" / "episodes"
            episodes_dir.mkdir(parents=True, exist_ok=True)
            (episodes_dir / "summary.json").write_text(
                "{ invalid json", encoding="utf-8"
            )

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["relay-task"],
            )

            trial = report["trials"][0]
            self.assertNotIn("episodes", trial)

    def test_trial_summary_omits_episodes_on_wrong_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("relay-task", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_episodes(
                trials_dir,
                trial_name,
                {"count": "2"},  # count should be int, not str
            )

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["relay-task"],
            )

            trial = report["trials"][0]
            self.assertNotIn("episodes", trial)

    def test_trial_summary_omits_episodes_when_items_mismatch_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("relay-task", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_episodes(
                trials_dir,
                trial_name,
                {
                    "count": 2,
                    "items": [{"index": 1}],  # only 1 item but count says 2
                },
            )

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["relay-task"],
            )

            trial = report["trials"][0]
            self.assertNotIn("episodes", trial)

    def test_trial_summary_omits_episodes_when_count_is_zero(self) -> None:
        # The attempt validator hard-requires episodes.count >= 1
        # (schemas.py _validate_task_attempt_episodes); a count of 0 passes
        # this reader's prior checks (isinstance int, len(items) == count)
        # so it must be rejected explicitly, the same way an out-of-range
        # item value must be (final-review.md Important 1).
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("relay-task", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_episodes(
                trials_dir,
                trial_name,
                {"count": 0, "items": []},
            )

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["relay-task"],
            )

            trial = report["trials"][0]
            self.assertNotIn("episodes", trial)

    def test_trial_summary_omits_episodes_when_reward_is_negative(self) -> None:
        # A verify_between task's tests/test.sh writing a sentinel -1 to
        # reward.txt on internal error is a real convention; the trial
        # summary must degrade to absent rather than pass the item
        # through, since the attempt validator hard-requires reward >= 0
        # (final-review.md Important 1).
        with tempfile.TemporaryDirectory() as temp_dir:
            trials_dir = Path(temp_dir)
            result = _trial_result("relay-task", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_episodes(
                trials_dir,
                trial_name,
                {
                    "count": 2,
                    "items": [
                        {"index": 1, "ended": "cap"},
                        {"index": 2, "ended": "natural", "reward": -1},
                    ],
                },
            )

            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["relay-task"],
            )

            trial = report["trials"][0]
            self.assertNotIn("episodes", trial)

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
                argv,
                harbor_command(
                    trials_dir / "harbor-run-config.json",
                    trials_dir=trials_dir,
                    secret_env=["ANTHROPIC_API_KEY"],
                ),
            )
            self.assertEqual(argv[:3], ["docker", "run", "--rm"])
            self.assertIn("-v", argv)
            self.assertIn("/var/run/docker.sock:/var/run/docker.sock", argv)
            self.assertIn(f"{trials_dir}:{trials_dir}", argv)
            self.assertIn("-e", argv)
            self.assertIn("ANTHROPIC_API_KEY", argv)
            self.assertIn("yacht/harbor-launcher:harbor-0.20.0", argv)
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
                        "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
                        "model_name": "claude-haiku-4-5",
                        "kwargs": {"version": "2.1.211"},
                        "env": {"ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"},
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
                "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
                "env": {"FFF_MODE": "mcp"},
                "mcp_servers": [
                    {"name": "fff", "command": "mcp-fff", "args": ["--stdio"]}
                ],
                "rigging_steps": [
                    {"method": "package", "target": "npm:@ff-labs/mcp-fff@0.3.0"}
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
        self.assertEqual(
            run_config["agents"][0]["kwargs"],
            {
                "version": "2.1.211",
                "rigging_steps": [
                    {"method": "package", "target": "npm:@ff-labs/mcp-fff@0.3.0"}
                ],
            },
        )

    def test_harbor_run_config_forwards_episode_plans(self) -> None:
        job = {
            "schema": "yacht.terminal-bench-job.v1",
            "dataset": {"name": "terminal-bench/terminal-bench-2", "version": "2.0"},
            "tasks": ["relay-task"],
            "vessel": "claude-baseline",
            "agent": {
                "name": "claude-code",
                "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
                "version": "2.1.211",
                "model": "claude-haiku-4-5",
                "env": {},
                "mcp_servers": [],
                "rigging_steps": [],
                "episodes": {
                    "relay-task": {
                        "max": 2,
                        "verify_between": False,
                        "instructions": ["x"],
                    }
                },
            },
        }

        config = harbor_run_config(job, trials_dir=Path("/tmp/trials"))

        self.assertEqual(
            config["agents"][0]["kwargs"]["episodes"]["relay-task"]["max"], 2
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

    def test_attempt_carries_episodes_block_and_metrics_are_unchanged(self) -> None:
        from yacht.courses.terminal_bench.attempts_from_trials import (
            write_terminal_bench_attempts_from_trials,
        )
        from yacht.courses.terminal_bench.harness import native_report_from_trials

        episodes_data = {
            "count": 2,
            "to_resolution": 2,
            "items": [
                {
                    "index": 1,
                    "ended": "cap",
                    "started_at": "2026-08-01T10:00:00Z",
                    "finished_at": "2026-08-01T10:01:00Z",
                    "usage": {"input_tokens": 500, "output_tokens": 200},
                    "cost_usd": 0.015,
                },
                {
                    "index": 2,
                    "ended": "natural",
                    "started_at": "2026-08-01T10:01:00Z",
                    "finished_at": "2026-08-01T10:02:00Z",
                    "usage": {"input_tokens": 400, "output_tokens": 150},
                    "cost_usd": 0.012,
                    "reward": 1.0,
                },
            ],
        }

        def _write_attempts(*, with_episodes: bool) -> dict[str, Any]:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                config_path = _write_config(root)
                logbook_dir = root / "logbook"
                write_terminal_bench_rollout_plan(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    vessel_name="claude-baseline",
                    comparison_name="claude-vs-claude-fff",
                )
                trials_dir = root / "trials"
                result = _trial_result("hello-world", reward=1)
                trial_name = result["trial_name"]
                _write_trial(trials_dir, result)
                if with_episodes:
                    _write_trial_episodes(trials_dir, trial_name, episodes_data)
                report = native_report_from_trials(
                    trials_dir=trials_dir,
                    roster_ids=["hello-world", "fix-permissions"],
                )
                with patch(
                    "yacht.courses.terminal_bench.attempts_from_trials."
                    "native_report_path_from_launcher_handoff",
                    return_value=_written_report(root, report),
                ):
                    write_terminal_bench_attempts_from_trials(
                        config_path=config_path,
                        logbook_dir=logbook_dir,
                        vessel_name="claude-baseline",
                        comparison_name="claude-vs-claude-fff",
                    )
                return json.loads(
                    (
                        logbook_dir
                        / "task-attempts/claude-vs-claude-fff/claude-baseline"
                        / "hello-world.json"
                    ).read_text(encoding="utf-8")
                )

        baseline_attempt = _write_attempts(with_episodes=False)
        episodic_attempt = _write_attempts(with_episodes=True)

        self.assertNotIn("episodes", baseline_attempt)
        self.assertEqual(episodic_attempt["episodes"], episodes_data)
        self.assertEqual(
            episodic_attempt["agent"]["machine_evidence"]["episodes"],
            episodes_data["items"],
        )
        self.assertEqual(episodic_attempt["metrics"], baseline_attempt["metrics"])

    def test_attempt_translation_survives_a_negative_reward_episode(self) -> None:
        # End-to-end guard for final-review.md Important 1: a task-authored
        # verifier writing reward=-1 must not raise SchemaValidationError
        # out of write_terminal_bench_attempts_from_trials and abort the
        # whole vessel's attempt translation — the episodes block degrades
        # to absent for that trial instead.
        from yacht.courses.terminal_bench.attempts_from_trials import (
            write_terminal_bench_attempts_from_trials,
        )
        from yacht.courses.terminal_bench.harness import native_report_from_trials

        episodes_data = {
            "count": 2,
            "to_resolution": 2,
            "items": [
                {
                    "index": 1,
                    "ended": "cap",
                    "started_at": "2026-08-01T10:00:00Z",
                    "finished_at": "2026-08-01T10:01:00Z",
                },
                {
                    "index": 2,
                    "ended": "natural",
                    "started_at": "2026-08-01T10:01:00Z",
                    "finished_at": "2026-08-01T10:02:00Z",
                    "reward": -1,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            write_terminal_bench_rollout_plan(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="claude-baseline",
                comparison_name="claude-vs-claude-fff",
            )
            trials_dir = root / "trials"
            result = _trial_result("hello-world", reward=1)
            trial_name = result["trial_name"]
            _write_trial(trials_dir, result)
            _write_trial_episodes(trials_dir, trial_name, episodes_data)
            report = native_report_from_trials(
                trials_dir=trials_dir,
                roster_ids=["hello-world", "fix-permissions"],
            )
            with patch(
                "yacht.courses.terminal_bench.attempts_from_trials."
                "native_report_path_from_launcher_handoff",
                return_value=_written_report(root, report),
            ):
                # Must not raise SchemaValidationError.
                write_terminal_bench_attempts_from_trials(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    vessel_name="claude-baseline",
                    comparison_name="claude-vs-claude-fff",
                )
            attempt = json.loads(
                (
                    logbook_dir
                    / "task-attempts/claude-vs-claude-fff/claude-baseline"
                    / "hello-world.json"
                ).read_text(encoding="utf-8")
            )

        self.assertNotIn("episodes", attempt)
        self.assertNotIn("episodes", attempt["agent"]["machine_evidence"])

    def test_metrics_sum_episode_usages_when_trial_usage_missing(self) -> None:
        from yacht.courses.terminal_bench.attempts_from_trials import _metrics

        trial = {
            "started_at": "2026-08-01T10:00:00Z",
            "finished_at": "2026-08-01T10:02:00Z",
            "episodes": {
                "count": 2,
                "items": [
                    {
                        "index": 1,
                        "ended": "natural",
                        "usage": {"input_tokens": 10, "output_tokens": 2},
                    },
                    {
                        "index": 2,
                        "ended": "natural",
                        "usage": {"input_tokens": 5, "output_tokens": 3},
                    },
                ],
            },
        }
        self.assertEqual(_metrics(trial)["tokens"], 20)

    def test_metrics_stay_unmeasured_if_any_episode_lacks_usage(self) -> None:
        from yacht.courses.terminal_bench.attempts_from_trials import _metrics

        trial = {
            "episodes": {
                "count": 2,
                "items": [
                    {
                        "index": 1,
                        "ended": "natural",
                        "usage": {"input_tokens": 10, "output_tokens": 2},
                    },
                    {"index": 2, "ended": "timeout"},
                ],
            },
        }
        self.assertEqual(_metrics(trial)["tokens"], 0)


def _written_report(root: Path, report: dict[str, Any]) -> Path:
    report_path = root / "native-report" / "claude-baseline.run-1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


class TerminalBenchInstallOnlyTests(unittest.TestCase):
    def _run(self, root, fake_runner, vessel_name="claude-baseline"):
        from yacht.courses.terminal_bench.install_only import (
            run_terminal_bench_install_only,
        )

        regatta = load_regatta(_write_config(root))
        return run_terminal_bench_install_only(
            regatta=regatta,
            vessel_name=vessel_name,
            work_dir=root / "install-only",
            command_runner=fake_runner,
        )

    def test_passes_when_install_trial_records_agent_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            commands = []

            def fake_runner(argv, cwd):
                commands.append(argv)
                _write_trial(
                    root / "install-only",
                    _trial_result("hello-world", reward=None),
                )
                return CommandResult(exit_code=0, stdout="", stderr="")

            summary = self._run(root, fake_runner)

            self.assertEqual(summary["status"], "passed")
            self.assertEqual(
                summary["evidence"]["agent"],
                {"name": "claude-code", "version": "2.1.211"},
            )
            self.assertNotIn("resolved_version", summary["evidence"])
            self.assertEqual(summary["evidence"]["task"], "hello-world")
            self.assertEqual(commands[0][-1], "--install-only")
            run_config = json.loads(
                (root / "install-only/harbor-run-config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(run_config["datasets"][0]["task_names"], ["hello-world"])

    def test_omp_install_only_requires_resolved_version_to_match_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_dir = root / "evals" / "convention-task"
            task_dir.mkdir(parents=True)
            (task_dir / "instruction.md").write_text("solve\n", encoding="utf-8")
            (task_dir / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
            (task_dir / "task.toml").write_text(
                '[metadata]\nauthor = "yacht"\ndescription = "x"\n'
                'difficulty = "easy"\n\n[verifier]\ntimeout_sec = 60.0\n\n'
                "[agent]\ntimeout_sec = 300.0\n",
                encoding="utf-8",
            )
            config_path = root / "regatta.toml"
            config_path.write_text(
                f"""
[regatta]
name = "omp-install-only"

[course]
name = "tiny"

[[course.tasks]]
id = "convention-task"
title = "Task"

[course.adapter]
kind = "custom-eval"
dataset = "{root / "evals"}"
split = "v1"
harness = "harbor"

[secrets.openai]
source = "env"
name = "OPENAI_API_KEY"

[runtimes.harbor-omp]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "omp"
harness_version = "17.2.15"
required_secrets = ["openai"]

[[vessels]]
name = "omp-baseline"
model = "openai/gpt-5.2"
runtime = "harbor-omp"
""",
                encoding="utf-8",
            )
            from yacht.courses.terminal_bench.install_only import (
                run_terminal_bench_install_only,
            )

            def fake_runner(argv, cwd):
                result = {
                    "task_name": "convention-task",
                    "trial_name": "convention-task__abc1234",
                    "agent_info": {"name": "omp", "version": "17.2.15"},
                }
                _write_trial(root / "install-only", result)
                resolved = (
                    root
                    / "install-only"
                    / "harbor"
                    / "convention-task__abc1234"
                    / "agent"
                )
                resolved.mkdir(parents=True)
                (resolved / "resolved-version.txt").write_text(
                    "omp/9.9.9\n", encoding="utf-8"
                )
                return CommandResult(exit_code=0, stdout="", stderr="")

            summary = run_terminal_bench_install_only(
                regatta=load_regatta(config_path),
                vessel_name="omp-baseline",
                work_dir=root / "install-only",
                command_runner=fake_runner,
            )

            self.assertEqual(summary["status"], "failed")
            self.assertIn("does not match configured pin", summary["evidence"]["error"])
            self.assertEqual(summary["evidence"]["resolved_version"], "omp/9.9.9")
            self.assertEqual(summary["evidence"]["expected_version"], "17.2.15")

    def test_fails_when_harbor_run_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            summary = self._run(
                root,
                lambda argv, cwd: CommandResult(exit_code=3, stdout="", stderr="boom"),
            )

            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["evidence"]["exit_code"], 3)
            self.assertEqual(summary["evidence"]["stderr"], "boom")

    def test_fails_when_no_trial_result_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            summary = self._run(
                root,
                lambda argv, cwd: CommandResult(exit_code=0, stdout="", stderr=""),
            )

            self.assertEqual(summary["status"], "failed")
            self.assertIn("no trial result", summary["evidence"]["error"])

    def test_fails_when_install_raises_in_container(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def fake_runner(argv, cwd):
                _write_trial(
                    root / "install-only",
                    _trial_result("hello-world", exception=True),
                )
                return CommandResult(exit_code=0, stdout="", stderr="")

            summary = self._run(root, fake_runner)

            self.assertEqual(summary["status"], "failed")
            self.assertEqual(
                summary["evidence"]["exception"]["type"], "AgentTimeoutError"
            )


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
                    secret_values={"anthropic": "test-secret"},
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
                {
                    "backend": "harbor",
                    "image": "yacht/harbor-launcher:harbor-0.20.0",
                },
            )
            self.assertEqual(attempt["metrics"]["tokens"], 1650)
            self.assertEqual(attempt["metrics"]["duration_seconds"], 300.0)
            evidence = attempt["agent"]["machine_evidence"]
            self.assertEqual(evidence["format"], "terminal-bench-harbor-trial")
            self.assertEqual(evidence["reward"], 1.0)
            self.assertEqual(evidence["cost"], {"total": 0.0123})
            self.assertEqual(len(native_launches), 2)
            self.assertEqual(
                native_launches[0][:3],
                native_harness_command("yacht.courses.terminal_bench.harness"),
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


PI_MCP_EXAMPLE_CONFIG = Path("examples/custom-eval-pi-mcp-ab-smoke.toml")


def _load_harbor_rigging_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "containers/harbor-launcher/yacht_harbor_agents/rigging.py"
    )
    spec = importlib.util.spec_from_file_location(
        "yacht_harbor_agents_rigging_seam", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderJobRenderingTests(unittest.TestCase):
    def test_provider_vessel_ships_rendered_config_not_mcp_servers(self) -> None:
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)

        job = render_terminal_bench_job(regatta=regatta, vessel_name="pi-with-mcp")

        agent = job["agent"]
        self.assertEqual(agent["mcp_servers"], [])
        methods = [step["method"] for step in agent["rigging_steps"]]
        self.assertIn("agent-extension", methods)
        config_steps = [
            step
            for step in agent["rigging_steps"]
            if step["method"] == "config-file"
            and step["target"] == ".pi/agent/mcp.json"
        ]
        self.assertEqual(len(config_steps), 1)
        content = json.loads(config_steps[0]["content"])
        self.assertEqual(
            content["settings"], {"directTools": True, "toolPrefix": "mcp"}
        )
        self.assertIn("files", content["mcpServers"])

    def test_rejects_mcp_server_step_with_no_native_support_and_no_provider(
        self,
    ) -> None:
        config = PI_MCP_EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
            'tools = ["pi-mcp-adapter", "files"]', 'tools = ["files"]'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                ConfigError,
                "does not support rigging install method mcp-server and no "
                "rigged tool provides it",
            ):
                render_terminal_bench_job(regatta=regatta, vessel_name="pi-with-mcp")

    def test_rigging_steps_run_through_the_harbor_launcher(self) -> None:
        rigging_module = _load_harbor_rigging_module()
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)
        job = render_terminal_bench_job(regatta=regatta, vessel_name="pi-with-mcp")

        commands = rigging_module.rigging_commands(job["agent"]["rigging_steps"])

        self.assertEqual(len(commands), 3)

    def test_claude_code_native_path_is_unchanged(self) -> None:
        regatta = load_regatta(Path("examples/custom-eval-mcp-ab-smoke.toml"))

        job = render_terminal_bench_job(regatta=regatta, vessel_name="claude-with-mcp")

        self.assertEqual(
            [server["name"] for server in job["agent"]["mcp_servers"]], ["files"]
        )


CUSTOM_EVAL_EPISODIC_CONFIG = """
[regatta]
name = "custom-eval-episodic"

[preflight]
failure_policy = "abort-group"

[course]
name = "relay-course"

[[course.tasks]]
id = "relay-task"
title = "Relay task with an episode plan"

[course.adapter]
kind = "custom-eval"
dataset = "evals"
split = "v1"
harness = "harbor"

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.harbor-claude]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "claude-code"
harness_version = "2.1.211"
required_secrets = ["anthropic"]

[runtimes.harbor-pi]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "pi"
harness_version = "0.74.0"
required_secrets = ["anthropic"]

[[vessels]]
name = "claude-baseline"
model = "claude-haiku-4-5"
runtime = "harbor-claude"

[[vessels]]
name = "pi-baseline"
model = "anthropic/claude-haiku-4-5"
runtime = "harbor-pi"

[[comparisons]]
name = "claude-vs-pi"
course = "relay-course"
vessels = ["claude-baseline", "pi-baseline"]
"""


def _write_custom_eval_relay_task(root: Path, *, episodes_table: str | None) -> Path:
    tasks_dir = root / "evals"
    task_dir = tasks_dir / "relay-task"
    task_dir.mkdir(parents=True)
    (task_dir / "instruction.md").write_text("episode one\n", encoding="utf-8")
    body = (
        "[metadata]\n"
        'author = "yacht"\n'
        'description = "Episodic relay smoke task."\n'
        'difficulty = "easy"\n'
        "\n"
        "[verifier]\n"
        "timeout_sec = 60.0\n"
        "\n"
        "[agent]\n"
        "timeout_sec = 300.0\n"
    )
    if episodes_table is not None:
        body += "\n" + episodes_table
    (task_dir / "task.toml").write_text(body, encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text(
        "#!/bin/bash\nset -uo pipefail\nexit 0\n", encoding="utf-8"
    )
    environment_dir = task_dir / "environment"
    environment_dir.mkdir()
    (environment_dir / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
    if episodes_table is not None:
        episodes_dir = task_dir / "episodes"
        episodes_dir.mkdir()
        (episodes_dir / "002.md").write_text("delta two\n", encoding="utf-8")
    return tasks_dir


def _write_custom_eval_episodic_config(root: Path) -> Path:
    config_path = root / "regatta.toml"
    config_path.write_text(CUSTOM_EVAL_EPISODIC_CONFIG, encoding="utf-8")
    return config_path


class EpisodicJobRenderingTests(unittest.TestCase):
    def test_render_job_embeds_episode_plans_for_episodic_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_custom_eval_relay_task(root, episodes_table="[episodes]\nmax = 2\n")
            config_path = _write_custom_eval_episodic_config(root)
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(
                regatta=regatta, vessel_name="claude-baseline"
            )

        self.assertEqual(
            job["agent"]["episodes"]["relay-task"]["instructions"], ["delta two\n"]
        )
        self.assertEqual(job["agent"]["episodes"]["relay-task"]["max"], 2)

    def test_render_job_omits_episodes_key_when_no_task_is_episodic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_custom_eval_relay_task(root, episodes_table=None)
            config_path = _write_custom_eval_episodic_config(root)
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(
                regatta=regatta, vessel_name="claude-baseline"
            )

        self.assertNotIn("episodes", job["agent"])

    def test_render_job_rejects_episodic_tasks_on_pi(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_custom_eval_relay_task(root, episodes_table="[episodes]\nmax = 2\n")
            config_path = _write_custom_eval_episodic_config(root)
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(ConfigError, "pi"):
                render_terminal_bench_job(regatta=regatta, vessel_name="pi-baseline")

    def test_render_job_embeds_episode_plans_for_omp_and_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_custom_eval_relay_task(root, episodes_table="[episodes]\nmax = 2\n")
            config_path = root / "regatta.toml"
            config_path.write_text(
                f"""
[regatta]
name = "relay-omp-codex"

[course]
name = "relay-course"

[[course.tasks]]
id = "relay-task"
title = "Relay"

[course.adapter]
kind = "custom-eval"
dataset = "{root / "evals"}"
split = "v1"
harness = "harbor"

[secrets.openai]
source = "env"
name = "OPENAI_API_KEY"

[runtimes.harbor-omp]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "omp"
harness_version = "17.2.15"
required_secrets = ["openai"]

[runtimes.harbor-codex]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "codex"
harness_version = "0.147.0"
required_secrets = ["openai"]

[[vessels]]
name = "omp-baseline"
model = "openai/gpt-5.2"
runtime = "harbor-omp"

[[vessels]]
name = "codex-baseline"
model = "openai/gpt-5.2"
runtime = "harbor-codex"
""",
                encoding="utf-8",
            )
            regatta = load_regatta(config_path)
            expected = {
                "omp-baseline": "yacht_harbor_agents.agents:YachtOmp",
                "codex-baseline": "yacht_harbor_agents.agents:YachtCodex",
            }
            for vessel, import_path in expected.items():
                with self.subTest(vessel=vessel):
                    job = render_terminal_bench_job(regatta=regatta, vessel_name=vessel)
                    self.assertEqual(job["agent"]["import_path"], import_path)
                    self.assertEqual(job["agent"]["episodes"]["relay-task"]["max"], 2)
                    self.assertIn("episodes", job["agent"])


if __name__ == "__main__":
    unittest.main()
