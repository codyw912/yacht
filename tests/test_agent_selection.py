import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.agent_selection import configured_agent_name
from yacht.cli import main
from yacht.regatta import ConfigError


class AgentSelectionTests(unittest.TestCase):
    def test_selects_single_configured_agent_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            self.assertEqual(configured_agent_name(config_path), "pi")

    def test_requires_at_least_one_configured_agent_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                """
[regatta]
name = "empty"

[course]
name = "swe-bench-lite"
tasks = [
  { id = "django__django-11099", title = "Fix a regression", difficulty = 3 },
]

[[vessels]]
name = "unconfigured"
model = "test"

[[vessels]]
name = "also-unconfigured"
model = "test"

[[comparisons]]
name = "unconfigured-comparison"
course = "swe-bench-lite"
vessels = ["unconfigured", "also-unconfigured"]
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError,
                "require exactly one configured agent harness; found none",
            ):
                configured_agent_name(config_path)

    def test_rejects_multiple_configured_agent_harnesses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(
                PI_WITH_FFF_CONFIG
                + """
[runtimes.codex]
backend = "container"
agent = "codex"
image = "yacht/codex-agent-runtime:test"
command = ["codex"]

[[vessels]]
name = "codex-baseline"
model = "gpt-5"
runtime = "codex"

[[comparisons]]
name = "pi-vs-codex"
course = "swe-bench-lite"
vessels = ["pi-baseline", "codex-baseline"]
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError,
                "require exactly one configured agent harness; found codex, pi",
            ):
                configured_agent_name(config_path)

    def test_real_benchmark_command_uses_configured_agent_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(
                """
[regatta]
name = "codex-comparison"

[course]
name = "swe-bench-lite"
tasks = [
  { id = "django__django-11099", title = "Fix a regression", difficulty = 3 },
]

[course.adapter]
kind = "swe-bench"
dataset = "princeton-nlp/SWE-bench_Lite"
split = "test"
harness = "docker"

[runtimes.codex]
backend = "container"
agent = "codex"
image = "yacht/codex-agent-runtime:test"
command = ["codex"]

[[vessels]]
name = "codex-baseline"
model = "gpt-5"
runtime = "codex"

[[vessels]]
name = "codex-challenger"
model = "gpt-5"
runtime = "codex"

[[comparisons]]
name = "codex-vs-codex"
course = "swe-bench-lite"
vessels = ["codex-baseline", "codex-challenger"]
""",
                encoding="utf-8",
            )
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "real-benchmark-eval",
                        str(config_path),
                        "--logbook",
                        str(root / "logbook"),
                        "--workspace",
                        str(root),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "unsupported agent preflight adapter codex",
                stderr.getvalue(),
            )


if __name__ == "__main__":
    unittest.main()
