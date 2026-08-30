import unittest
from pathlib import Path

from yacht.domain.model import load_regatta


PI_AGENT_IMAGE = "yacht/pi-agent-runtime:pi-0.74.0"
PI_AGENT_VERSION = "0.74.0"
PI_AGENT_PACKAGE = "@earendil-works/pi-coding-agent"
CLAUDE_CODE_VERSION = "2.1.211"
CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"
OMP_VERSION = "17.2.15"
OMP_PACKAGE = "@oh-my-pi/pi-coding-agent"
BUN_VERSION = "1.3.14"
CODEX_VERSION = "0.147.0"
CODEX_PACKAGE = "@openai/codex"


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
        self.assertEqual(rigging.install[0].method, "agent-extension")
        self.assertEqual(rigging.install[0].target, "npm:@ff-labs/pi-fff")
        self.assertEqual(rigging.install[0].agent, "pi")
        self.assertEqual(rigging.env["PI_FFF_MODE"], "required")
        self.assertIn("fffind", rigging.instructions)
        self.assertEqual(
            rigging.preflight.checks[2].expect_tool_calls,
            ("fffind",),
        )
        self.assertEqual(regatta.vessels[1].rigging, ("pi-fff",))
        self.assertEqual(regatta.course.tasks[0].id, "container-pi-fff-smoke-1")

    def test_real_container_pi_fff_benchmark_smoke_uses_swe_bench_runtime(self) -> None:
        regatta = load_regatta(
            Path("examples/container-pi-fff-real-benchmark-smoke.toml")
        )
        runtime = regatta.runtime_recipes["pi-container"]
        rigging = regatta.rigging_recipes["pi-fff"]

        self.assertEqual(regatta.course.name, "swe-bench-lite")
        self.assertIsNotNone(regatta.course.adapter)
        assert regatta.course.adapter is not None
        self.assertEqual(regatta.course.adapter.kind, "swe-bench")
        self.assertEqual(len(regatta.course.tasks), 1)
        self.assertEqual(regatta.course.tasks[0].id, "django__django-11099")
        assert regatta.course.adapter.selection is not None
        self.assertEqual(regatta.course.adapter.selection.seed, 0)
        self.assertEqual(regatta.course.adapter.selection.requested_instances, 1)
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
        self.assertEqual(rigging.install[0].method, "agent-extension")
        self.assertEqual(rigging.install[0].target, "npm:@ff-labs/pi-fff")
        self.assertEqual(rigging.install[0].agent, "pi")
        self.assertEqual(regatta.vessels[0].name, "pi-container-baseline")
        self.assertEqual(regatta.vessels[1].name, "pi-container-fff")
        self.assertEqual(regatta.vessels[1].rigging, ("pi-fff",))

    def test_real_container_pi_fff_benchmark_small_has_explicit_task_set(self) -> None:
        regatta = load_regatta(
            Path("examples/container-pi-fff-real-benchmark-small.toml")
        )
        runtime = regatta.runtime_recipes["pi-container"]

        self.assertEqual(regatta.name, "container-pi-fff-real-benchmark-small")
        self.assertEqual(regatta.course.name, "swe-bench-lite")
        self.assertIsNotNone(regatta.course.adapter)
        self.assertEqual(
            [task.id for task in regatta.course.tasks],
            ["django__django-11099", "django__django-11179"],
        )
        self.assertEqual(runtime.image, PI_AGENT_IMAGE)
        self.assertEqual(runtime.required_secrets, ("anthropic",))
        self.assertEqual(regatta.vessels[0].name, "pi-container-baseline")
        self.assertEqual(regatta.vessels[1].name, "pi-container-fff")
        self.assertEqual(regatta.vessels[1].rigging, ("pi-fff",))

    def test_claude_code_mcp_example_pins_tool_and_renders_mcp_server(self) -> None:
        regatta = load_regatta(
            Path("examples/container-claude-code-mcp-real-task-smoke.toml")
        )
        runtime = regatta.runtime_recipes["claude-code-container"]
        rigging = regatta.rigging_recipes["fff-mcp"]

        self.assertEqual(
            runtime.image,
            f"yacht/claude-code-runtime:claude-{CLAUDE_CODE_VERSION}",
        )
        self.assertEqual(runtime.harness, "claude-code")
        self.assertEqual(runtime.required_secrets, ("anthropic",))
        self.assertEqual(
            runtime.command,
            ("claude", "--model", "claude-haiku-4-5"),
        )
        self.assertEqual(rigging.install[0].method, "package")
        self.assertEqual(rigging.install[0].target, "npm:@ff-labs/mcp-fff@0.3.0")
        self.assertEqual(rigging.install[1].method, "mcp-server")
        self.assertEqual(rigging.install[1].target, "fff")
        self.assertEqual(rigging.install[1].command, ("mcp-fff", "--stdio"))
        self.assertEqual(
            rigging.preflight.checks[1].expect_tool_calls,
            ("mcp__fff__fffind",),
        )
        self.assertEqual(regatta.vessels[1].rigging, ("fff-mcp",))
        self.assertEqual(
            regatta.course.tasks[0].id,
            "container-claude-code-mcp-smoke-1",
        )

    def test_claude_code_dockerfile_builds_pinned_claude_code(self) -> None:
        dockerfile = Path("containers/claude-code-runtime/Dockerfile")
        contents = dockerfile.read_text(encoding="utf-8")

        self.assertIn(f"ARG CLAUDE_CODE_VERSION={CLAUDE_CODE_VERSION}", contents)
        self.assertIn(
            f"npm install -g {CLAUDE_CODE_PACKAGE}@$CLAUDE_CODE_VERSION",
            contents,
        )
        self.assertIn("WORKDIR /workspace", contents)
        self.assertIn("USER yacht", contents)

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

    def test_omp_and_codex_dockerfiles_build_pinned_clis(self) -> None:
        omp = Path("containers/omp-runtime/Dockerfile").read_text(encoding="utf-8")
        self.assertIn(f"ARG OMP_VERSION={OMP_VERSION}", omp)
        self.assertIn(f"ARG BUN_VERSION={BUN_VERSION}", omp)
        self.assertIn("npm install -g bun@$BUN_VERSION", omp)
        self.assertIn(f"npm install -g {OMP_PACKAGE}@$OMP_VERSION", omp)
        self.assertIn("USER yacht", omp)

        codex = Path("containers/codex-runtime/Dockerfile").read_text(encoding="utf-8")
        self.assertIn(f"ARG CODEX_VERSION={CODEX_VERSION}", codex)
        self.assertIn(f"npm install -g {CODEX_PACKAGE}@$CODEX_VERSION", codex)
        self.assertIn("USER yacht", codex)

    def test_omp_and_codex_smoke_examples_pin_harbor_preflight(self) -> None:
        omp = load_regatta(Path("examples/custom-eval-omp-skill-ab-smoke.toml"))
        omp_runtime = omp.runtime_recipes["harbor-omp"]
        self.assertEqual(omp_runtime.harness, "omp")
        self.assertEqual(omp_runtime.harness_version, "17.2.15")
        self.assertEqual(
            [check.name for check in omp_runtime.preflight.checks],
            [
                "docker-daemon",
                "harbor-launcher-image",
                "openai-secret",
                "workspace-writable",
                "agent-install",
            ],
        )
        self.assertEqual(omp_runtime.preflight.checks[2].kind, "env")
        self.assertEqual(omp_runtime.preflight.checks[4].kind, "install-only")

        codex = load_regatta(Path("examples/custom-eval-codex-skill-ab-smoke.toml"))
        codex_runtime = codex.runtime_recipes["harbor-codex"]
        self.assertEqual(codex_runtime.harness, "codex")
        self.assertEqual(codex_runtime.harness_version, "0.147.0")
        self.assertEqual(
            [check.kind for check in codex_runtime.preflight.checks],
            ["command", "command", "env", "command", "install-only"],
        )

    def test_omp_and_codex_container_smokes_use_repo_owned_images(self) -> None:
        omp = load_regatta(Path("examples/container-omp-runtime-smoke.toml"))
        self.assertEqual(
            omp.runtime_recipes["omp-container"].image,
            "yacht/omp-runtime:omp-17.2.15",
        )
        self.assertEqual(omp.runtime_recipes["omp-container"].backend, "container")
        self.assertEqual(omp.runtime_recipes["omp-container"].command, ("omp",))

        codex = load_regatta(Path("examples/container-codex-runtime-smoke.toml"))
        self.assertEqual(
            codex.runtime_recipes["codex-container"].image,
            "yacht/codex-runtime:codex-0.147.0",
        )
        self.assertEqual(codex.runtime_recipes["codex-container"].backend, "container")
        self.assertEqual(codex.runtime_recipes["codex-container"].command, ("codex",))
