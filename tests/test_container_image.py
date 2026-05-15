import unittest
from pathlib import Path

from yacht.regatta import load_regatta


PI_AGENT_IMAGE = "yacht/pi-agent-runtime:pi-0.74.0"
PI_AGENT_VERSION = "0.74.0"
PI_AGENT_PACKAGE = "@earendil-works/pi-coding-agent"


class ContainerImageTests(unittest.TestCase):
    def test_pi_container_runtime_smoke_example_uses_repo_owned_image(self) -> None:
        regatta = load_regatta(Path("examples/container-pi-runtime-smoke.toml"))
        runtime = regatta.runtime_recipes["pi-container"]

        self.assertEqual(runtime.image, PI_AGENT_IMAGE)
        self.assertEqual(runtime.backend, "container")
        self.assertEqual(runtime.command, ("pi",))
        self.assertEqual(runtime.required_secrets, ())
        self.assertEqual(
            [check.name for check in runtime.preflight.checks],
            ["pi-present", "runtime-home-isolated"],
        )

    def test_container_fff_example_uses_repo_owned_image(self) -> None:
        regatta = load_regatta(Path("examples/container-pi-fff-provisioning.toml"))

        self.assertEqual(
            regatta.runtime_recipes["pi-container"].image,
            PI_AGENT_IMAGE,
        )

    def test_real_container_pi_task_smoke_uses_tiny_anthropic_runtime(self) -> None:
        regatta = load_regatta(Path("examples/container-pi-real-task-smoke.toml"))
        runtime = regatta.runtime_recipes["pi-container"]

        self.assertEqual(runtime.image, PI_AGENT_IMAGE)
        self.assertEqual(runtime.required_secrets, ("anthropic",))
        self.assertEqual(
            runtime.command,
            (
                "pi",
                "--provider",
                "anthropic",
                "--model",
                "haiku",
                "--print",
                "--mode",
                "json",
                "--no-tools",
            ),
        )
        self.assertEqual(regatta.course.tasks[0].id, "container-pi-real-smoke-1")

    def test_real_container_pi_fff_task_smoke_uses_rigged_runtime(self) -> None:
        regatta = load_regatta(Path("examples/container-pi-fff-real-task-smoke.toml"))
        runtime = regatta.runtime_recipes["pi-container"]
        rigging = regatta.rigging_recipes["pi-fff"]

        self.assertEqual(runtime.image, PI_AGENT_IMAGE)
        self.assertEqual(runtime.required_secrets, ("anthropic",))
        self.assertEqual(
            runtime.command,
            (
                "pi",
                "--provider",
                "anthropic",
                "--model",
                "haiku",
                "--print",
                "--mode",
                "json",
            ),
        )
        self.assertEqual(rigging.install, ("npm:@ff-labs/pi-fff",))
        self.assertEqual(rigging.env["PI_FFF_MODE"], "required")
        self.assertIn("fffind", rigging.instructions)
        self.assertEqual(
            rigging.preflight.checks[2].expect_tool_calls,
            ("fffind",),
        )
        self.assertEqual(regatta.vessels[1].rigging, ("pi-fff",))
        self.assertEqual(regatta.course.tasks[0].id, "container-pi-fff-smoke-1")

    def test_pi_container_dockerfile_builds_pinned_pi_agent(self) -> None:
        dockerfile = Path("containers/pi-agent-runtime/Dockerfile")
        contents = dockerfile.read_text(encoding="utf-8")

        self.assertIn(f"ARG PI_CODING_AGENT_VERSION={PI_AGENT_VERSION}", contents)
        self.assertIn(
            f"npm install -g {PI_AGENT_PACKAGE}@$PI_CODING_AGENT_VERSION",
            contents,
        )
        self.assertIn("WORKDIR /workspace", contents)
        self.assertIn("USER yacht", contents)
