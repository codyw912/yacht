import unittest

from yacht.domain.model import RiggingInstallStep, RiggingRecipe, RuntimeRecipe
from yacht.runtimes.rigging_setup import RiggingSetupError, plan_rigging_setup


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
            "runtime backend host-nix does not support rigging install method package yet",
        ):
            plan_rigging_setup(
                runtime=runtime,
                riggings=(rigging,),
                command_prefix=("nix", "develop", "--command"),
            )


if __name__ == "__main__":
    unittest.main()
