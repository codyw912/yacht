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
from yacht.preflight.runner import build_preflight_execution_plan
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.runtimes.instances import build_runtime_instances_plan
from yacht.runtimes.instances import write_runtime_instances_plan
from yacht.runtimes.plan import build_runtime_plan


class RuntimePlanTests(unittest.TestCase):
    def test_build_runtime_instances_plan_resolves_container_paths_and_env(
        self,
    ) -> None:
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
                "yacht/pi-agent-runtime:pi-0.74.0",
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
                    "--env",
                    "HOME=/home/yacht",
                    "--env",
                    "PATH=/home/yacht/.local/state/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
                    "--env",
                    "NPM_CONFIG_CACHE=/home/yacht/.cache/npm",
                    "--env",
                    "NPM_CONFIG_PREFIX=/home/yacht/.local/state/npm-global",
                    "--env",
                    "XDG_CONFIG_HOME=/home/yacht/.config",
                    "--env",
                    "XDG_CACHE_HOME=/home/yacht/.cache",
                    "--env",
                    "XDG_STATE_HOME=/home/yacht/.local/state",
                    "--env",
                    "PI_FFF_MODE=required",
                    "--env",
                    "FFF_FRECENCY_DB=/home/yacht/.local/state/fff-frecency.sqlite",
                    "--env",
                    "FFF_HISTORY_DB=/home/yacht/.local/state/fff-history.sqlite",
                    "--env",
                    "ANTHROPIC_API_KEY",
                    "--mount",
                    f"type=bind,source={workspace_path},target=/workspace",
                    "--mount",
                    (
                        "type=bind,"
                        f"source={logbook_dir / 'runtime' / 'container-pi' / 'pi-container-fff' / 'home'},"
                        "target=/home/yacht"
                    ),
                    "yacht/pi-agent-runtime:pi-0.74.0",
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
                "yacht/pi-agent-runtime:pi-0.74.0",
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
                    "--env",
                    "HOME=/home/yacht",
                    "--env",
                    "PATH=/home/yacht/.local/state/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
                    "--env",
                    "NPM_CONFIG_CACHE=/home/yacht/.cache/npm",
                    "--env",
                    "NPM_CONFIG_PREFIX=/home/yacht/.local/state/npm-global",
                    "--env",
                    "XDG_CONFIG_HOME=/home/yacht/.config",
                    "--env",
                    "XDG_CACHE_HOME=/home/yacht/.cache",
                    "--env",
                    "XDG_STATE_HOME=/home/yacht/.local/state",
                    "--mount",
                    "type=bind,source={workspace},target=/workspace",
                    "--mount",
                    "type=bind,source={trial_home},target=/home/yacht",
                    "yacht/pi-agent-runtime:pi-0.74.0",
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
            self.assertEqual(
                plan["tool_capabilities"],
                [
                    {
                        "name": "fff",
                        "kind": "code-navigation",
                        "description": "Codebase memory and navigation tool.",
                        "interfaces": ["agent-tool"],
                        "install_methods": ["agent-extension"],
                        "expected_tool_calls": ["fffind", "ffgrep"],
                    }
                ],
            )
            self.assertEqual(
                plan["surfaces"],
                {
                    "agent_harnesses": ["pi"],
                    "tools": ["fff"],
                    "benchmark": {
                        "name": "swe-bench-lite",
                        "adapter": "swe-bench",
                        "dataset": "princeton-nlp/SWE-bench_Lite",
                        "split": "test",
                        "execution_harness": "docker",
                    },
                },
            )
            comparison = plan["comparisons"][0]
            self.assertEqual(comparison["name"], "pi-vs-pi-fff")
            rigged = comparison["vessels"][1]
            self.assertEqual(rigged["name"], "pi-plus-fff")
            self.assertEqual(rigged["harness"], "pi")
            self.assertEqual(rigged["agent"], "pi")
            self.assertEqual(
                rigged["surfaces"],
                {
                    "agent_harness": "pi",
                    "tools": ["fff"],
                },
            )
            self.assertEqual(
                rigged["install"],
                [
                    {
                        "method": "agent-extension",
                        "target": "npm:@ff-labs/pi-fff",
                        "agent": "pi",
                        "package": "@ff-labs/pi-fff",
                    }
                ],
            )
            self.assertEqual(
                rigged["rigging_capabilities"],
                {
                    "status": "supported",
                    "runtime_backend": "host-nix",
                    "runtime_harness": "pi",
                    "runtime_agent": "pi",
                    "supported_install_methods": [
                        "agent-extension",
                        "config-file",
                        "mcp-server",
                        "package",
                        "preinstalled",
                        "custom-command",
                    ],
                    "install_checks": [
                        {
                            "origin": "rigging",
                            "origin_name": "pi-fff",
                            "method": "agent-extension",
                            "target": "npm:@ff-labs/pi-fff",
                            "supported": True,
                        }
                    ],
                    "tools": [
                        {
                            "name": "fff",
                            "kind": "code-navigation",
                            "description": "Codebase memory and navigation tool.",
                            "interfaces": ["agent-tool"],
                            "install_methods": ["agent-extension"],
                            "expected_tool_calls": ["fffind", "ffgrep"],
                        }
                    ],
                },
            )
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
                plan["surfaces"],
                {
                    "agent_harnesses": ["pi"],
                    "tools": ["fff"],
                    "benchmark": {
                        "name": "swe-bench-lite",
                        "adapter": "swe-bench",
                        "dataset": "princeton-nlp/SWE-bench_Lite",
                        "split": "test",
                        "execution_harness": "docker",
                    },
                },
            )
            self.assertEqual(
                plan["tool_capabilities"],
                [
                    {
                        "name": "fff",
                        "kind": "code-navigation",
                        "description": "Codebase memory and navigation tool.",
                        "interfaces": ["agent-tool"],
                        "install_methods": ["agent-extension"],
                        "expected_tool_calls": ["fffind", "ffgrep"],
                    }
                ],
            )
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
            self.assertEqual(
                rigged_vessel["surfaces"],
                {
                    "agent_harness": "pi",
                    "tools": ["fff"],
                },
            )
            self.assertEqual(rigged_vessel["runtime"]["harness"], "pi")
            self.assertEqual(rigged_vessel["runtime"]["agent"], "pi")
            self.assertEqual(
                rigged_vessel["install"],
                [
                    {
                        "method": "agent-extension",
                        "target": "npm:@ff-labs/pi-fff",
                        "agent": "pi",
                        "package": "@ff-labs/pi-fff",
                    }
                ],
            )
            self.assertEqual(
                rigged_vessel["rigging_capabilities"]["status"],
                "supported",
            )
            self.assertEqual(
                rigged_vessel["rigging_capabilities"]["supported_install_methods"],
                [
                    "agent-extension",
                    "config-file",
                    "mcp-server",
                    "package",
                    "preinstalled",
                    "custom-command",
                ],
            )
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
                ["fffind"],
            )

    def test_build_runtime_plan_infers_agent_surface_from_runtime_command(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace('harness = "pi"\n', "").replace(
            'tools = ["fff"]\n',
            "",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            plan = build_runtime_plan(config_path)

            self.assertEqual(plan["surfaces"]["agent_harnesses"], ["pi"])
            self.assertEqual(plan["surfaces"]["tools"], [])
            self.assertEqual(plan["vessels"][1]["surfaces"]["agent_harness"], "pi")
            self.assertNotIn("tools", plan["vessels"][1]["surfaces"])

    def test_build_runtime_plan_includes_custom_tool_capability_metadata(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            '[riggings.pi-fff]\ntools = ["fff"]',
            """[tools.repo-map]
kind = "code-navigation"
description = "Repository map sidecar."
interfaces = ["mcp-server", "agent-tool"]
install_methods = ["mcp-server"]
expected_tool_calls = ["repo_map"]

[riggings.pi-fff]
tools = ["repo-map"]""",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            plan = build_runtime_plan(config_path)

            self.assertEqual(
                plan["tool_capabilities"],
                [
                    {
                        "name": "repo-map",
                        "kind": "code-navigation",
                        "description": "Repository map sidecar.",
                        "interfaces": ["mcp-server", "agent-tool"],
                        "install_methods": ["mcp-server"],
                        "expected_tool_calls": ["repo_map"],
                    }
                ],
            )
            self.assertEqual(
                plan["vessels"][1]["rigging_capabilities"]["tools"],
                plan["tool_capabilities"],
            )

    def test_build_runtime_plan_reports_unsupported_install_capability(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            'method = "agent-extension"',
            'method = "mcp-server"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            plan = build_runtime_plan(config_path)

            capabilities = plan["vessels"][1]["rigging_capabilities"]
            self.assertEqual(capabilities["status"], "unsupported")
            self.assertEqual(
                capabilities["install_checks"],
                [
                    {
                        "origin": "rigging",
                        "origin_name": "pi-fff",
                        "method": "mcp-server",
                        "target": "npm:@ff-labs/pi-fff",
                        "supported": False,
                        "reason": (
                            "runtime harness pi does not support rigging "
                            "install method mcp-server and no rigged tool "
                            "provides it"
                        ),
                    }
                ],
            )

    def test_plan_command_prints_resolved_runtime_plan_without_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["internals", "plan", str(config_path)])

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
                        "internals",
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
                        "internals",
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
                exit_code = main(["internals", "plan", str(config_path)])

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
