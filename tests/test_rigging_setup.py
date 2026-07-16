import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import RiggingInstallStep, RiggingRecipe, RuntimeRecipe
from yacht.runtimes.rigging_setup import (
    RiggingSetupError,
    RiggingSetupFile,
    RiggingSetupPlan,
    apply_rigging_setup,
    plan_rigging_setup,
)


def _runtime() -> RuntimeRecipe:
    return RuntimeRecipe(
        name="pi-container",
        backend="container",
        harness="pi",
        image="yacht/pi-agent-runtime:pi-0.74.0",
        command=("pi",),
    )


class RiggingSetupTests(unittest.TestCase):
    def test_plans_agent_extension_install_with_runtime_base_command(self) -> None:
        runtime = RuntimeRecipe(
            name="pi-container",
            backend="container",
            harness="pi",
            image="yacht/pi-agent-runtime:pi-0.74.0",
            command=("pi", "--provider", "anthropic", "--print"),
        )
        rigging = RiggingRecipe(
            name="pi-fff",
            install=(
                RiggingInstallStep(
                    method="agent-extension",
                    target="npm:@ff-labs/pi-fff",
                    agent="pi",
                ),
            ),
        )

        plan = plan_rigging_setup(
            runtime=runtime,
            riggings=(rigging,),
            command_prefix=("docker", "run", "image"),
        )

        self.assertEqual(len(plan.commands), 1)
        self.assertEqual(plan.commands[0].origin_name, "pi-fff")
        self.assertEqual(plan.commands[0].target, "npm:@ff-labs/pi-fff")
        self.assertEqual(
            plan.commands[0].argv,
            ("docker", "run", "image", "pi", "install", "npm:@ff-labs/pi-fff"),
        )

    def test_preinstalled_rigging_does_not_emit_setup_command(self) -> None:
        runtime = RuntimeRecipe(
            name="local",
            backend="host-nix",
            harness="local-smoke",
            command=("local-agent",),
        )
        rigging = RiggingRecipe(
            name="local-tool",
            install=(
                RiggingInstallStep(
                    method="preinstalled",
                    target="local-smoke",
                ),
            ),
        )

        plan = plan_rigging_setup(
            runtime=runtime,
            riggings=(rigging,),
            command_prefix=("nix", "develop", "--command"),
        )

        self.assertEqual(plan.commands, ())

    def test_plans_custom_command_inside_runtime(self) -> None:
        runtime = RuntimeRecipe(
            name="custom-runtime",
            backend="container",
            harness="local-smoke",
            command=("local-agent",),
        )
        rigging = RiggingRecipe(
            name="custom-tool",
            install=(
                RiggingInstallStep(
                    method="custom-command",
                    target="custom-tool",
                    command=("toolctl", "install", "custom-tool"),
                ),
            ),
        )

        plan = plan_rigging_setup(
            runtime=runtime,
            riggings=(rigging,),
            command_prefix=("docker", "run", "image"),
        )

        self.assertEqual(
            plan.commands[0].argv,
            ("docker", "run", "image", "toolctl", "install", "custom-tool"),
        )

    def test_rejects_custom_command_without_command(self) -> None:
        runtime = RuntimeRecipe(
            name="custom-runtime",
            backend="container",
            harness="local-smoke",
            command=("local-agent",),
        )
        rigging = RiggingRecipe(
            name="custom-tool",
            install=(
                RiggingInstallStep(
                    method="custom-command",
                    target="custom-tool",
                ),
            ),
        )

        with self.assertRaisesRegex(
            RiggingSetupError,
            "custom-command install requires command",
        ):
            plan_rigging_setup(
                runtime=runtime,
                riggings=(rigging,),
                command_prefix=("docker", "run", "image"),
            )

    def test_rejects_unsupported_install_before_planning_commands(self) -> None:
        runtime = RuntimeRecipe(
            name="pi",
            backend="host-nix",
            harness="pi",
            command=("pi",),
        )
        rigging = RiggingRecipe(
            name="unsupported",
            install=(
                RiggingInstallStep(
                    method="package",
                    target="ripgrep",
                ),
            ),
        )

        with self.assertRaisesRegex(
            RiggingSetupError,
            "package install target ripgrep is not supported yet",
        ):
            plan_rigging_setup(
                runtime=runtime,
                riggings=(rigging,),
                command_prefix=("nix", "develop", "--command"),
            )

    def test_plans_npm_package_install_through_command_prefix(self) -> None:
        rigging = RiggingRecipe(
            name="tool",
            install=(RiggingInstallStep(method="package", target="npm:some-tool"),),
        )

        plan = plan_rigging_setup(
            runtime=_runtime(),
            riggings=(rigging,),
            command_prefix=("docker", "run", "image"),
        )

        self.assertEqual(
            plan.commands[0].argv,
            ("docker", "run", "image", "npm", "install", "-g", "some-tool"),
        )

    def test_plans_config_file_as_setup_file(self) -> None:
        rigging = RiggingRecipe(
            name="tool",
            install=(
                RiggingInstallStep(
                    method="config-file",
                    target=".config/tool/settings.json",
                    content='{"enabled": true}',
                ),
            ),
        )

        plan = plan_rigging_setup(
            runtime=_runtime(),
            riggings=(rigging,),
            command_prefix=("docker", "run", "image"),
        )

        self.assertEqual(plan.commands, ())
        self.assertEqual(len(plan.files), 1)
        self.assertEqual(plan.files[0].target, ".config/tool/settings.json")

    def test_rejects_config_file_target_outside_trial_home(self) -> None:
        rigging = RiggingRecipe(
            name="tool",
            install=(
                RiggingInstallStep(
                    method="config-file",
                    target="../outside.json",
                    content="{}",
                ),
            ),
        )

        with self.assertRaisesRegex(
            RiggingSetupError,
            "must be a relative path inside the trial home",
        ):
            plan_rigging_setup(
                runtime=_runtime(),
                riggings=(rigging,),
                command_prefix=(),
            )


class ApplyRiggingSetupTests(unittest.TestCase):
    def test_writes_config_file_into_trial_home_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_home = Path(temp_dir) / "home"
            temp_home.mkdir()
            plan = RiggingSetupPlan(
                commands=(),
                files=(
                    RiggingSetupFile(
                        origin_name="tool",
                        target=".config/tool/settings.json",
                        content='{"enabled": true}',
                    ),
                ),
            )

            results = apply_rigging_setup(
                plan=plan,
                env={},
                workspace_path=Path(temp_dir),
                setup_runner=lambda argv, env, cwd: None,
                temp_home=temp_home,
            )

            written = temp_home / ".config" / "tool" / "settings.json"
            self.assertEqual(written.read_text(encoding="utf-8"), '{"enabled": true}')
            self.assertEqual(results[0].action, "config-file")
            self.assertEqual(results[0].exit_code, 0)
            self.assertIn(str(written.resolve()), results[0].stdout)

    def test_blocks_file_write_that_escapes_trial_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_home = Path(temp_dir) / "home"
            temp_home.mkdir()
            plan = RiggingSetupPlan(
                commands=(),
                files=(
                    RiggingSetupFile(
                        origin_name="tool",
                        target="safe/../../escape.json",
                        content="{}",
                    ),
                ),
            )

            with self.assertRaisesRegex(RiggingSetupError, "escapes the trial home"):
                apply_rigging_setup(
                    plan=plan,
                    env={},
                    workspace_path=Path(temp_dir),
                    setup_runner=lambda argv, env, cwd: None,
                    temp_home=temp_home,
                )
            self.assertFalse((Path(temp_dir) / "escape.json").exists())


if __name__ == "__main__":
    unittest.main()
