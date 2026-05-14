import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.fixtures import REGATTA_CONFIG
from tests.test_provisioning import CONTAINER_PI_CONFIG, PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.preflight_runner import build_preflight_execution_plan
from yacht.runtime_instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.runtime_instances import build_runtime_instances_plan
from yacht.runtime_instances import write_runtime_instances_plan
from yacht.runtime_plan import build_runtime_plan


class RuntimePlanTests(unittest.TestCase):
    def test_build_runtime_instances_plan_resolves_container_paths_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            config_path.write_text(CONTAINER_PI_CONFIG, encoding="utf-8")

            plan = build_runtime_instances_plan(
                config_path,
                logbook_dir,
                workspace_path,
            )

            vessel = plan["comparisons"][0]["vessels"][1]
            self.assertEqual(vessel["name"], "pi-container-fff")
            self.assertEqual(vessel["runtime"], "pi-container")
            self.assertEqual(vessel["backend"], "container")
            self.assertEqual(
                vessel["image"],
                "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1",
            )
            self.assertEqual(vessel["container_home"], "/home/yacht")
            self.assertEqual(vessel["container_workspace"], "/workspace")
            self.assertEqual(
                vessel["command_prefix"],
                [
                    "docker",
                    "run",
                    "--rm",
                    "--workdir",
                    "/workspace",
                    "--mount",
                    f"type=bind,source={workspace_path},target=/workspace",
                    "--mount",
                    (
                        "type=bind,"
                        f"source={logbook_dir / 'runtime' / 'container-pi' / 'pi-container-fff' / 'home'},"
                        "target=/home/yacht"
                    ),
                    "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1",
                ],
            )
            self.assertEqual(vessel["command"], ["pi"])
            self.assertEqual(vessel["env"]["HOME"], "/home/yacht")
            self.assertEqual(
                vessel["env"]["NPM_CONFIG_PREFIX"],
                "/home/yacht/.local/state/npm-global",
            )
            self.assertEqual(
                vessel["env"]["FFF_HISTORY_DB"],
                "/home/yacht/.local/state/fff-history.sqlite",
            )
            self.assertEqual(
                vessel["cleanup_paths"],
                [str(logbook_dir / "runtime" / "container-pi" / "pi-container-fff")],
            )

    def test_build_runtime_plan_includes_container_runtime_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(CONTAINER_PI_CONFIG, encoding="utf-8")

            plan = build_runtime_plan(config_path)

            runtime = plan["vessels"][1]["runtime"]
            self.assertEqual(runtime["backend"], "container")
            self.assertEqual(
                runtime["image"],
                "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1",
            )
            self.assertEqual(runtime["container_home"], "/home/yacht")
            self.assertEqual(runtime["container_workspace"], "/workspace")
            self.assertEqual(
                runtime["command_prefix"],
                [
                    "docker",
                    "run",
                    "--rm",
                    "--workdir",
                    "/workspace",
                    "--mount",
                    "type=bind,source={workspace},target=/workspace",
                    "--mount",
                    "type=bind,source={trial_home},target=/home/yacht",
                    "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1",
                ],
            )
            self.assertEqual(
                plan["vessels"][1]["env"]["FFF_HISTORY_DB"],
                "/home/yacht/.local/state/fff-history.sqlite",
            )
            self.assertEqual(plan["vessels"][1]["env"]["HOME"], "/home/yacht")

    def test_build_runtime_instances_plan_resolves_host_nix_paths_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            plan = build_runtime_instances_plan(
                config_path,
                logbook_dir,
                workspace_path,
            )

            self.assertEqual(plan["regatta"], "pi-fff-comparison")
            self.assertEqual(plan["course"], "swe-bench-lite")
            self.assertEqual(plan["mode"], "dry-run")
            comparison = plan["comparisons"][0]
            self.assertEqual(comparison["name"], "pi-vs-pi-fff")
            rigged = comparison["vessels"][1]
            self.assertEqual(rigged["name"], "pi-plus-fff")
            self.assertEqual(rigged["runtime"], "pi")
            self.assertEqual(rigged["backend"], "host-nix")
            self.assertEqual(
                rigged["command_prefix"],
                ["nix", "develop", "path:.#pi", "--command"],
            )
            self.assertEqual(rigged["command"], ["pi"])
            self.assertEqual(
                rigged["trial_root"],
                str(logbook_dir / "runtime" / "pi-vs-pi-fff" / "pi-plus-fff"),
            )
            self.assertEqual(
                rigged["temp_home"],
                str(logbook_dir / "runtime" / "pi-vs-pi-fff" / "pi-plus-fff" / "home"),
            )
            self.assertEqual(rigged["workspace_path"], str(workspace_path))
            self.assertEqual(
                rigged["cleanup_paths"],
                [str(logbook_dir / "runtime" / "pi-vs-pi-fff" / "pi-plus-fff")],
            )
            self.assertEqual(
                rigged["env"]["HOME"],
                str(logbook_dir / "runtime" / "pi-vs-pi-fff" / "pi-plus-fff" / "home"),
            )
            self.assertEqual(rigged["env"]["PI_FFF_MODE"], "required")
            self.assertEqual(
                rigged["env"]["FFF_HISTORY_DB"],
                str(
                    logbook_dir
                    / "runtime"
                    / "pi-vs-pi-fff"
                    / "pi-plus-fff"
                    / "home"
                    / ".local"
                    / "state"
                    / "fff-history.sqlite"
                ),
            )
            self.assertEqual(rigged["env"]["ANTHROPIC_API_KEY"], "{secret:anthropic}")
            self.assertEqual(
                rigged["secret_refs"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "redacted": True,
                    }
                ],
            )
            self.assertFalse(logbook_dir.exists())

    def test_write_runtime_instances_plan_persists_redacted_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            plan = write_runtime_instances_plan(
                config_path,
                logbook_dir,
                workspace_path,
            )

            artifact_path = logbook_dir / RUNTIME_INSTANCES_PLAN_PATH
            saved = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(saved, plan)
            self.assertEqual(plan["schema"], "yacht.runtime-instances.v1")
            self.assertEqual(
                plan["comparisons"][0]["vessels"][1]["env"]["ANTHROPIC_API_KEY"],
                "{secret:anthropic}",
            )
            self.assertFalse((logbook_dir / "runtime").exists())

    def test_build_runtime_plan_redacts_secrets_and_merges_rigging_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            plan = build_runtime_plan(config_path)

            self.assertEqual(plan["regatta"], "pi-fff-comparison")
            self.assertEqual(plan["course"], "swe-bench-lite")
            self.assertEqual(plan["preflight_failure_policy"], "abort-group")
            self.assertEqual(
                plan["course_adapter"],
                {
                    "kind": "swe-bench",
                    "dataset": "princeton-nlp/SWE-bench_Lite",
                    "split": "test",
                    "harness": "docker",
                    "task_ids": ["django__django-11099"],
                    "grading": {
                        "delegated_to": "swe-bench",
                        "execution": "docker-harness",
                        "status": "planned",
                    },
                },
            )
            self.assertEqual(
                plan["comparisons"],
                [
                    {
                        "name": "pi-vs-pi-fff",
                        "course": "swe-bench-lite",
                        "vessels": ["pi-baseline", "pi-plus-fff"],
                        "preflight_failure_policy": "abort-group",
                    }
                ],
            )

            rigged_vessel = plan["vessels"][1]
            self.assertEqual(rigged_vessel["name"], "pi-plus-fff")
            self.assertEqual(rigged_vessel["runtime"]["backend"], "host-nix")
            self.assertEqual(
                rigged_vessel["runtime"]["command_prefix"],
                ["nix", "develop", "path:.#pi", "--command"],
            )
            self.assertEqual(rigged_vessel["runtime"]["command"], ["pi"])
            self.assertEqual(
                rigged_vessel["env"]["HOME"],
                "{trial_home}",
            )
            self.assertEqual(
                rigged_vessel["env"]["FFF_HISTORY_DB"],
                "{trial_state}/fff-history.sqlite",
            )
            self.assertEqual(
                rigged_vessel["secret_refs"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "redacted": True,
                    }
                ],
            )
            self.assertEqual(
                [check["name"] for check in rigged_vessel["preflight_checks"]],
                [
                    "pi-present",
                    "runtime-home-isolated",
                    "fff-mode",
                    "fff-state-isolated",
                    "fff-headless-smoke",
                ],
            )
            self.assertEqual(
                rigged_vessel["preflight_checks"][-1]["expect_tool_calls"],
                ["fff"],
            )

    def test_plan_command_prints_resolved_runtime_plan_without_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["plan", str(config_path)])

            self.assertEqual(exit_code, 0)
            self.assertFalse(logbook_dir.exists())
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["regatta"], "pi-fff-comparison")
            self.assertEqual(payload["vessels"][0]["name"], "pi-baseline")

    def test_runtime_instances_command_prints_dry_run_without_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "runtime-instances",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertFalse(logbook_dir.exists())
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(
                payload["comparisons"][0]["vessels"][1]["env"]["ANTHROPIC_API_KEY"],
                "{secret:anthropic}",
            )

    def test_runtime_instances_command_writes_logbook_artifact_when_requested(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "runtime-instances",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--write-logbook",
                    ]
                )

            self.assertEqual(exit_code, 0)
            artifact_path = logbook_dir / RUNTIME_INSTANCES_PLAN_PATH
            saved = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(saved, json.loads(stdout.getvalue()))
            self.assertEqual(saved["schema"], "yacht.runtime-instances.v1")
            self.assertFalse((logbook_dir / "runtime").exists())

    def test_plan_command_reports_missing_runtime_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(REGATTA_CONFIG, encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["plan", str(config_path)])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: vessels[0].runtime is required",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_build_preflight_execution_plan_resolves_check_inclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_dir.mkdir()

            plan = build_preflight_execution_plan(
                config_path,
                logbook_dir,
                workspace_dir,
                agent_preflight="none",
            )

            self.assertEqual(plan["mode"], "dry-run")
            self.assertEqual(plan["agent_preflight"], "none")
            comparison = plan["comparisons"][0]
            self.assertEqual(comparison["name"], "pi-vs-pi-fff")
            baseline = comparison["vessels"][0]
            rigged = comparison["vessels"][1]
            self.assertEqual(
                [check["name"] for check in baseline["preflight_checks"]],
                ["pi-present", "runtime-home-isolated"],
            )
            agent_check = _check_by_name(rigged, "fff-headless-smoke")
            self.assertFalse(agent_check["included"])
            self.assertEqual(
                agent_check["omitted_reason"],
                "agent preflight disabled",
            )

            with_agent = build_preflight_execution_plan(
                config_path,
                logbook_dir,
                workspace_dir,
                agent_preflight="pi",
            )
            rigged_with_agent = with_agent["comparisons"][0]["vessels"][1]
            included_agent_check = _check_by_name(
                rigged_with_agent,
                "fff-headless-smoke",
            )
            self.assertTrue(included_agent_check["included"])
            self.assertEqual(included_agent_check["prompt"], "preflights/pi-fff.md")
            self.assertEqual(
                included_agent_check["transcript_dir"],
                str(logbook_dir / "transcripts" / "pi-vs-pi-fff" / "pi-plus-fff"),
            )


def _check_by_name(vessel: dict[str, object], name: str) -> dict[str, object]:
    checks = vessel["preflight_checks"]
    assert isinstance(checks, list)
    for check in checks:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
