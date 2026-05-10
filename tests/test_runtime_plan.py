import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.fixtures import REGATTA_CONFIG
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.preflight_runner import build_preflight_execution_plan
from yacht.runtime_plan import build_runtime_plan


class RuntimePlanTests(unittest.TestCase):
    def test_build_runtime_plan_redacts_secrets_and_merges_rigging_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            plan = build_runtime_plan(config_path)

            self.assertEqual(plan["regatta"], "pi-fff-comparison")
            self.assertEqual(plan["course"], "swe-bench-lite")
            self.assertEqual(plan["preflight_failure_policy"], "abort-group")
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
                ["nix", "develop", "github:example/yacht-runtimes#pi", "--command"],
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
