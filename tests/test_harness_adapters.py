import unittest

from yacht.harnesses.registry import agent_prompt_runner_factory
from yacht.harnesses.registry import harness_adapter
from yacht.harnesses.registry import supported_agent_preflight_names
from yacht.harnesses.registry import supported_harness_names
from yacht.harnesses.registry import supported_task_attempt_names
from yacht.harnesses.registry import task_agent
from yacht.harnesses.claude_code import ClaudeCodeAdapter
from yacht.harnesses.codex import CodexAdapter
from yacht.harnesses.local_smoke import LocalSmokeAgentAdapter
from yacht.harnesses.omp import OmpAdapter
from yacht.harnesses.pi import PiAdapter
from yacht.domain.model import ConfigError


class HarnessAdapterRegistryTests(unittest.TestCase):
    def test_lists_supported_harnesses_for_cli_choices(self) -> None:
        self.assertEqual(
            supported_harness_names(),
            ("claude-code", "codex", "local-smoke", "omp", "pi"),
        )
        self.assertEqual(
            supported_agent_preflight_names(),
            ("none", "claude-code", "codex", "local-smoke", "omp", "pi"),
        )
        self.assertEqual(
            supported_task_attempt_names(),
            ("claude-code", "codex", "local-smoke", "omp", "pi"),
        )

    def test_resolves_registered_task_agents(self) -> None:
        self.assertIsInstance(task_agent("claude-code"), ClaudeCodeAdapter)
        self.assertIsInstance(task_agent("codex"), CodexAdapter)
        self.assertIsInstance(task_agent("local-smoke"), LocalSmokeAgentAdapter)
        self.assertIsInstance(task_agent("omp"), OmpAdapter)
        self.assertIsInstance(task_agent("pi"), PiAdapter)

    def test_resolves_registered_preflight_factories(self) -> None:
        self.assertIsNone(agent_prompt_runner_factory("none"))
        self.assertIsNotNone(agent_prompt_runner_factory("claude-code"))
        self.assertIsNotNone(agent_prompt_runner_factory("codex"))
        self.assertIsNotNone(agent_prompt_runner_factory("local-smoke"))
        self.assertIsNotNone(agent_prompt_runner_factory("omp"))
        self.assertIsNotNone(agent_prompt_runner_factory("pi"))

    def test_reports_unknown_harnesses_with_surface_specific_errors(self) -> None:
        with self.assertRaisesRegex(ConfigError, "unsupported harness adapter unknown"):
            harness_adapter("unknown")
        with self.assertRaisesRegex(
            ConfigError,
            "unsupported agent preflight adapter unknown",
        ):
            agent_prompt_runner_factory("unknown")
        with self.assertRaisesRegex(
            ConfigError,
            "unsupported task attempt agent unknown",
        ):
            task_agent("unknown")


if __name__ == "__main__":
    unittest.main()
