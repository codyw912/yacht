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


if __name__ == "__main__":
    unittest.main()
