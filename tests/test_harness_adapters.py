import unittest

from yacht.harness_adapters import agent_prompt_runner_factory
from yacht.harness_adapters import harness_adapter
from yacht.harness_adapters import supported_agent_preflight_names
from yacht.harness_adapters import supported_harness_names
from yacht.harness_adapters import supported_task_attempt_names
from yacht.harness_adapters import task_agent
from yacht.local_smoke_adapter import LocalSmokeAgentAdapter
from yacht.pi_adapter import PiAdapter
from yacht.regatta import ConfigError


class HarnessAdapterRegistryTests(unittest.TestCase):
    def test_lists_supported_harnesses_for_cli_choices(self) -> None:
        self.assertEqual(supported_harness_names(), ("local-smoke", "pi"))
        self.assertEqual(
            supported_agent_preflight_names(),
            ("none", "local-smoke", "pi"),
        )
        self.assertEqual(supported_task_attempt_names(), ("local-smoke", "pi"))

    def test_resolves_registered_task_agents(self) -> None:
        self.assertIsInstance(task_agent("local-smoke"), LocalSmokeAgentAdapter)
        self.assertIsInstance(task_agent("pi"), PiAdapter)

    def test_resolves_registered_preflight_factories(self) -> None:
        self.assertIsNone(agent_prompt_runner_factory("none"))
        self.assertIsNotNone(agent_prompt_runner_factory("local-smoke"))
        self.assertIsNotNone(agent_prompt_runner_factory("pi"))

    def test_reports_unknown_harnesses_with_surface_specific_errors(self) -> None:
        with self.assertRaisesRegex(ConfigError, "unsupported harness adapter codex"):
            harness_adapter("codex")
        with self.assertRaisesRegex(
            ConfigError,
            "unsupported agent preflight adapter codex",
        ):
            agent_prompt_runner_factory("codex")
        with self.assertRaisesRegex(
            ConfigError,
            "unsupported task attempt agent codex",
        ):
            task_agent("codex")


if __name__ == "__main__":
    unittest.main()
