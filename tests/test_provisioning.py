import tempfile
import unittest
from pathlib import Path

from yacht.regatta import ConfigError, load_regatta
from yacht.schemas import PREFLIGHT_SCHEMA, validate_preflight_document


PI_WITH_FFF_CONFIG = """
[regatta]
name = "pi-fff-comparison"

[preflight]
failure_policy = "abort-group"

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

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.pi]
backend = "host-nix"
flake = "path:.#pi"
command = ["pi"]
required_secrets = ["anthropic"]

[runtimes.pi.preflight]
required = true
checks = [
  { name = "pi-present", kind = "command", command = ["pi", "--version"] },
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[riggings.pi-fff]
install = ["npm:@ff-labs/pi-fff"]
instructions = "Use fff for codebase memory and navigation."

[riggings.pi-fff.env]
PI_FFF_MODE = "required"
FFF_FRECENCY_DB = "{trial_state}/fff-frecency.sqlite"
FFF_HISTORY_DB = "{trial_state}/fff-history.sqlite"

[riggings.pi-fff.preflight]
required = true
checks = [
  { name = "fff-mode", kind = "env", env = ["PI_FFF_MODE"] },
  { name = "fff-state-isolated", kind = "path-isolation", env = ["FFF_FRECENCY_DB", "FFF_HISTORY_DB"] },
  { name = "fff-headless-smoke", kind = "agent-prompt", prompt = "preflights/pi-fff.md", expect_tool_calls = ["fff"] },
]

[[vessels]]
name = "pi-baseline"
model = "claude-sonnet"
runtime = "pi"

[[vessels]]
name = "pi-plus-fff"
model = "claude-sonnet"
runtime = "pi"
rigging = ["pi-fff"]

[[comparisons]]
name = "pi-vs-pi-fff"
course = "swe-bench-lite"
vessels = ["pi-baseline", "pi-plus-fff"]
"""


CONTAINER_PI_CONFIG = """
[regatta]
name = "container-pi-comparison"

[course]
name = "tiny-smoke"
tasks = [
  { id = "smoke-1", title = "Container smoke", difficulty = 1 },
]

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.pi-container]
backend = "container"
image = "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1"
command = ["pi"]
container_home = "/home/yacht"
container_workspace = "/workspace"
required_secrets = ["anthropic"]

[runtimes.pi-container.preflight]
checks = [
  { name = "pi-present", kind = "command", command = ["pi", "--version"] },
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[riggings.pi-fff]
install = ["npm:@ff-labs/pi-fff"]
instructions = "Use fff for codebase memory and navigation."

[riggings.pi-fff.env]
PI_FFF_MODE = "required"
FFF_FRECENCY_DB = "{trial_state}/fff-frecency.sqlite"
FFF_HISTORY_DB = "{trial_state}/fff-history.sqlite"

[[vessels]]
name = "pi-container-baseline"
model = "claude-sonnet"
runtime = "pi-container"

[[vessels]]
name = "pi-container-fff"
model = "claude-sonnet"
runtime = "pi-container"
rigging = ["pi-fff"]

[[comparisons]]
name = "container-pi"
course = "tiny-smoke"
vessels = ["pi-container-baseline", "pi-container-fff"]
"""


class ProvisioningConfigTests(unittest.TestCase):
    def test_loads_baseline_and_rigged_vessels_on_the_same_course(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")

            regatta = load_regatta(config_path)

            self.assertEqual(regatta.course.name, "swe-bench-lite")
            self.assertEqual(
                [vessel.name for vessel in regatta.vessels],
                ["pi-baseline", "pi-plus-fff"],
            )
            self.assertEqual(
                [vessel.runtime for vessel in regatta.vessels],
                ["pi", "pi"],
            )
            self.assertEqual(regatta.vessels[0].rigging, ())
            self.assertEqual(regatta.vessels[1].rigging, ("pi-fff",))
            self.assertEqual(regatta.runtime_recipes["pi"].backend, "host-nix")
            self.assertEqual(regatta.runtime_recipes["pi"].command, ("pi",))
            self.assertEqual(
                regatta.rigging_recipes["pi-fff"].env["PI_FFF_MODE"],
                "required",
            )
            self.assertEqual(regatta.secrets["anthropic"].name, "ANTHROPIC_API_KEY")
            self.assertEqual(regatta.preflight.failure_policy, "abort-group")
            self.assertEqual(
                [comparison.name for comparison in regatta.comparisons],
                ["pi-vs-pi-fff"],
            )
            self.assertEqual(
                regatta.comparisons[0].vessels,
                ("pi-baseline", "pi-plus-fff"),
            )
            self.assertEqual(
                regatta.runtime_recipes["pi"].preflight.checks[0].kind,
                "command",
            )
            self.assertEqual(
                regatta.rigging_recipes["pi-fff"].preflight.checks[2].prompt,
                "preflights/pi-fff.md",
            )
            self.assertIsNotNone(regatta.course.adapter)
            assert regatta.course.adapter is not None
            self.assertEqual(regatta.course.adapter.kind, "swe-bench")
            self.assertEqual(
                regatta.course.adapter.dataset,
                "princeton-nlp/SWE-bench_Lite",
            )
            self.assertEqual(regatta.course.adapter.split, "test")
            self.assertEqual(regatta.course.adapter.harness, "docker")

    def test_loads_container_runtime_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(CONTAINER_PI_CONFIG, encoding="utf-8")

            regatta = load_regatta(config_path)
            runtime = regatta.runtime_recipes["pi-container"]

            self.assertEqual(runtime.backend, "container")
            self.assertEqual(
                runtime.image,
                "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1",
            )
            self.assertEqual(runtime.flake, None)
            self.assertEqual(runtime.container_home, "/home/yacht")
            self.assertEqual(runtime.container_workspace, "/workspace")

    def test_swe_bench_course_adapter_requires_dataset_split_and_harness(self) -> None:
        cases = {
            "dataset": ('dataset = "princeton-nlp/SWE-bench_Lite"\n', ""),
            "split": ('split = "test"\n', ""),
            "harness": ('harness = "docker"\n', ""),
        }

        for field, (old, new) in cases.items():
            with self.subTest(field=field):
                config = PI_WITH_FFF_CONFIG.replace(old, new)
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "regatta.toml"
                    config_path.write_text(config, encoding="utf-8")

                    with self.assertRaisesRegex(
                        ConfigError,
                        f"course.adapter.{field} is required",
                    ):
                        load_regatta(config_path)

    def test_runtime_recipe_requires_backend_flake_and_command(self) -> None:
        cases = {
            "backend": ('backend = "host-nix"\n', ""),
            "flake": ('flake = "path:.#pi"\n', ""),
            "command": ('command = ["pi"]\n', ""),
        }

        for field, (old, new) in cases.items():
            with self.subTest(field=field):
                config = PI_WITH_FFF_CONFIG.replace(old, new)
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "regatta.toml"
                    config_path.write_text(config, encoding="utf-8")

                    with self.assertRaisesRegex(
                        ConfigError,
                        f"runtimes.pi.{field} is required",
                    ):
                        load_regatta(config_path)

    def test_container_runtime_requires_image_and_absolute_container_paths(self) -> None:
        cases = {
            "image": (
                'image = "ghcr.io/yacht/pi-agent-runtime:pi-0.73.1"\n',
                "",
                "runtimes.pi-container.image is required",
            ),
            "container_home": (
                'container_home = "/home/yacht"\n',
                'container_home = "home/yacht"\n',
                "runtimes.pi-container.container_home must be an absolute container path",
            ),
            "container_workspace": (
                'container_workspace = "/workspace"\n',
                'container_workspace = "workspace"\n',
                (
                    "runtimes.pi-container.container_workspace must be an "
                    "absolute container path"
                ),
            ),
        }

        for field, (old, new, message) in cases.items():
            with self.subTest(field=field):
                config = CONTAINER_PI_CONFIG.replace(old, new)
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "regatta.toml"
                    config_path.write_text(config, encoding="utf-8")

                    with self.assertRaisesRegex(ConfigError, message):
                        load_regatta(config_path)

    def test_secret_references_must_be_explicitly_provided(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            '[secrets.anthropic]\nsource = "env"\nname = "ANTHROPIC_API_KEY"\n\n',
            "",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "runtimes.pi.required_secrets references undefined secret anthropic",
            ):
                load_regatta(config_path)

    def test_comparison_vessels_must_reference_configured_vessels(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            'vessels = ["pi-baseline", "pi-plus-fff"]',
            'vessels = ["pi-baseline", "missing-vessel"]',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "comparisons\\[0\\].vessels references undefined vessel missing-vessel",
            ):
                load_regatta(config_path)

    def test_preflight_checks_validate_required_fields_for_their_kind(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            '{ name = "pi-present", kind = "command", command = ["pi", "--version"] }',
            '{ name = "pi-present", kind = "command" }',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "runtimes.pi.preflight.checks\\[0\\].command must contain",
            ):
                load_regatta(config_path)

    def test_example_agent_prompt_paths_exist(self) -> None:
        regatta = load_regatta(Path("examples/pi-fff-provisioning.toml"))
        prompt_paths = [
            check.prompt
            for rigging in regatta.rigging_recipes.values()
            for check in rigging.preflight.checks
            if check.kind == "agent-prompt" and check.prompt is not None
        ]

        self.assertEqual(prompt_paths, ["preflights/pi-fff.md"])
        for prompt_path in prompt_paths:
            self.assertTrue(Path(prompt_path).is_file(), prompt_path)

    def test_container_example_loads(self) -> None:
        regatta = load_regatta(Path("examples/container-pi-fff-provisioning.toml"))

        self.assertEqual(regatta.runtime_recipes["pi-container"].backend, "container")
        self.assertEqual(
            regatta.comparisons[0].vessels,
            ("pi-container-baseline", "pi-container-fff"),
        )

    def test_preflight_artifact_records_redacted_machine_and_agent_evidence(self) -> None:
        artifact = {
            "schema": PREFLIGHT_SCHEMA,
            "regatta": "pi-fff-comparison",
            "comparison": "pi-vs-pi-fff",
            "vessel": "pi-plus-fff",
            "runtime": "pi",
            "workspace_path": "/tmp/workspace",
            "temp_home": "/tmp/home",
            "command_prefix": [
                "nix",
                "develop",
                "path:.#pi",
                "--command",
            ],
            "cleanup_paths": ["/tmp/home"],
            "status": "passed",
            "failure_policy": "abort-group",
            "secret_refs": [
                {
                    "name": "anthropic",
                    "source": "env",
                    "ref": "ANTHROPIC_API_KEY",
                    "redacted": True,
                },
            ],
            "checks": [
                {
                    "name": "fff-headless-smoke",
                    "kind": "agent-prompt",
                    "origin": "rigging",
                    "origin_name": "pi-fff",
                    "required": True,
                    "status": "passed",
                    "evidence": {
                        "prompt": "preflights/pi-fff.md",
                        "tool_calls": ["fff"],
                    },
                },
            ],
        }

        validate_preflight_document(artifact)

        with self.assertRaisesRegex(ConfigError, "secret_refs\\[0\\].redacted"):
            invalid = artifact | {
                "secret_refs": [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "actual-secret-value",
                        "redacted": False,
                    },
                ],
            }
            try:
                validate_preflight_document(invalid)
            except ValueError as error:
                raise ConfigError(str(error)) from error


if __name__ == "__main__":
    unittest.main()
