import json
import tempfile
import unittest
from pathlib import Path

from yacht.config.loader import _parse_tool_capabilities
from yacht.contracts.schemas import SchemaValidationError, _validate_tool_capabilities
from yacht.courses.terminal_bench.attempts_from_trials import _observed_tool_calls
from yacht.domain.model import RiggingInstallStep, RiggingRecipe, RuntimeRecipe
from yacht.harnesses.mcp_config import (
    MCP_INSTALL_PROVIDERS,
    McpConfigError,
    provider_mcp_namespace,
    render_provider_mcp_config,
    supported_mcp_install_provider,
)
from yacht.harnesses.pi import PI_JSONL_EVIDENCE, tool_calls_from_pi_jsonl
from yacht.runtimes.capabilities import (
    rigging_capabilities_to_json,
    unsupported_rigging_capability_reasons,
)
from yacht.runtimes.tool_capabilities import (
    ProvidedInstall,
    ToolCapability,
    provided_mcp_install_provider,
)


class ProvidesDeclarationTests(unittest.TestCase):
    def test_tool_capability_declares_provided_install_method(self) -> None:
        capability = ToolCapability(
            name="pi-mcp-adapter",
            kind="mcp-adapter",
            provides=(ProvidedInstall(method="mcp-server", harness="pi"),),
        )

        self.assertEqual(
            capability.to_json()["provides"],
            [{"method": "mcp-server", "harness": "pi"}],
        )

    def test_to_json_omits_empty_provides(self) -> None:
        capability = ToolCapability(name="fff", kind="code-navigation")

        self.assertNotIn("provides", capability.to_json())

    def test_loader_parses_provides_from_tools_table(self) -> None:
        capabilities = _parse_tool_capabilities(
            {
                "tools": {
                    "pi-mcp-adapter": {
                        "kind": "mcp-adapter",
                        "install_methods": ["agent-extension"],
                        "provides": [
                            {"method": "mcp-server", "harness": "pi"},
                        ],
                    }
                }
            }
        )

        self.assertEqual(
            capabilities["pi-mcp-adapter"].provides,
            (ProvidedInstall(method="mcp-server", harness="pi"),),
        )


def _adapter_capability() -> ToolCapability:
    return ToolCapability(
        name="pi-mcp-adapter",
        kind="mcp-adapter",
        provides=(ProvidedInstall(method="mcp-server", harness="pi"),),
    )


class ProviderRegistryTests(unittest.TestCase):
    def test_pi_mcp_adapter_is_a_supported_provider_for_pi(self) -> None:
        self.assertTrue(supported_mcp_install_provider("pi-mcp-adapter", "pi"))
        self.assertFalse(
            supported_mcp_install_provider("pi-mcp-adapter", "claude-code")
        )
        self.assertFalse(supported_mcp_install_provider("other-adapter", "pi"))

    def test_renders_servers_and_observability_settings_in_one_document(self) -> None:
        provider = MCP_INSTALL_PROVIDERS[("pi-mcp-adapter", "pi")]
        step = RiggingInstallStep(
            method="mcp-server",
            target="files",
            command=("mcp-server-filesystem", "/app"),
        )

        render = render_provider_mcp_config(provider, (("pi-mcp-files", step),))

        self.assertEqual(render.target, ".pi/agent/mcp.json")
        self.assertEqual(
            json.loads(render.content),
            {
                "mcpServers": {
                    "files": {
                        "command": "mcp-server-filesystem",
                        "args": ["/app"],
                    }
                },
                "settings": {"directTools": True, "toolPrefix": "mcp"},
            },
        )
        self.assertEqual(
            [(entry.origin_name, entry.server_name) for entry in render.entries],
            [("pi-mcp-files", "files")],
        )

    def test_provider_render_requires_command_and_unique_server_names(self) -> None:
        provider = MCP_INSTALL_PROVIDERS[("pi-mcp-adapter", "pi")]
        no_command = RiggingInstallStep(method="mcp-server", target="files")

        with self.assertRaises(McpConfigError):
            render_provider_mcp_config(provider, (("rig", no_command),))

    def test_provider_render_rejects_duplicate_server_names(self) -> None:
        provider = MCP_INSTALL_PROVIDERS[("pi-mcp-adapter", "pi")]
        first = RiggingInstallStep(
            method="mcp-server", target="files", command=("mcp-server-filesystem",)
        )
        second = RiggingInstallStep(
            method="mcp-server", target="files", command=("mcp-server-filesystem-2",)
        )

        with self.assertRaises(McpConfigError):
            render_provider_mcp_config(
                provider, (("rig-one", first), ("rig-two", second))
            )


class ProviderNamespaceTests(unittest.TestCase):
    def test_pi_adapter_namespace_is_single_underscore_delimited(self) -> None:
        # pi-mcp-adapter's "mcp" toolPrefix names tools
        # mcp__<server>_<tool> with hyphens sanitized to underscores —
        # NOT Claude Code's mcp__<server>__<tool> convention.
        provider = MCP_INSTALL_PROVIDERS[("pi-mcp-adapter", "pi")]

        self.assertEqual(provider_mcp_namespace(provider, "files"), "mcp__files_")
        self.assertEqual(provider_mcp_namespace(provider, "repo-map"), "mcp__repo_map_")


class ProviderResolutionTests(unittest.TestCase):
    def test_resolves_provider_rigged_on_the_vessel(self) -> None:
        rigging = RiggingRecipe(name="pi-mcp-files", tools=("pi-mcp-adapter",))
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        provider = provided_mcp_install_provider("pi", (rigging,), capabilities)

        self.assertIsNotNone(provider)
        self.assertEqual(provider.tool_name, "pi-mcp-adapter")
        self.assertTrue(provider.pins_namespace)

    def test_no_provider_without_declaration_or_for_other_harness(self) -> None:
        rigging = RiggingRecipe(name="pi-mcp-files", tools=("pi-mcp-adapter",))
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        self.assertIsNone(
            provided_mcp_install_provider("claude-code", (rigging,), capabilities)
        )
        self.assertIsNone(provided_mcp_install_provider("pi", (rigging,), {}))
        self.assertIsNone(provided_mcp_install_provider("pi", (rigging,), None))
        self.assertIsNone(provided_mcp_install_provider(None, (rigging,), capabilities))

    def test_no_provider_when_declaration_has_no_matching_registry_entry(self) -> None:
        rigging = RiggingRecipe(name="mystery-mcp", tools=("mystery-adapter",))
        capabilities = {
            "mystery-adapter": ToolCapability(
                name="mystery-adapter",
                kind="mcp-adapter",
                provides=(ProvidedInstall(method="mcp-server", harness="pi"),),
            )
        }

        self.assertIsNone(provided_mcp_install_provider("pi", (rigging,), capabilities))


class ProvidesSchemaValidationTests(unittest.TestCase):
    def test_accepts_a_supported_provider_declaration(self) -> None:
        _validate_tool_capabilities(
            {
                "tools": {
                    "pi-mcp-adapter": {
                        "kind": "mcp-adapter",
                        "provides": [{"method": "mcp-server", "harness": "pi"}],
                    }
                }
            }
        )

    def test_rejects_a_provider_yacht_cannot_render_for(self) -> None:
        with self.assertRaises(SchemaValidationError):
            _validate_tool_capabilities(
                {
                    "tools": {
                        "mystery-adapter": {
                            "kind": "mcp-adapter",
                            "provides": [{"method": "mcp-server", "harness": "pi"}],
                        }
                    }
                }
            )

    def test_rejects_unknown_provided_methods(self) -> None:
        with self.assertRaises(SchemaValidationError):
            _validate_tool_capabilities(
                {
                    "tools": {
                        "pi-mcp-adapter": {
                            "kind": "mcp-adapter",
                            "provides": [{"method": "package", "harness": "pi"}],
                        }
                    }
                }
            )


def _pi_runtime(backend: str = "container") -> RuntimeRecipe:
    return RuntimeRecipe(
        name="pi-runtime",
        backend=backend,
        harness="pi",
        image="yacht/pi-agent-runtime:pi-0.74.0",
        command=("pi",),
    )


def _mcp_rigging() -> RiggingRecipe:
    return RiggingRecipe(
        name="pi-mcp-files",
        tools=("pi-mcp-adapter", "files"),
        install=(
            RiggingInstallStep(
                method="agent-extension",
                target="npm:pi-mcp-adapter@2.15.0",
                agent="pi",
            ),
            RiggingInstallStep(
                method="mcp-server",
                target="files",
                command=("mcp-server-filesystem", "/app"),
            ),
        ),
    )


class ProviderCapabilityGateTests(unittest.TestCase):
    def test_provider_unlocks_mcp_server_for_pi(self) -> None:
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        reasons = unsupported_rigging_capability_reasons(
            _pi_runtime(), (_mcp_rigging(),), capabilities
        )

        self.assertEqual(reasons, ())

    def test_provider_in_one_rigging_unlocks_mcp_server_in_another(self) -> None:
        adapter = RiggingRecipe(
            name="pi-adapter",
            tools=("pi-mcp-adapter",),
            install=(
                RiggingInstallStep(
                    method="agent-extension",
                    target="npm:pi-mcp-adapter@2.15.0",
                    agent="pi",
                ),
            ),
        )
        server = RiggingRecipe(
            name="files-mcp",
            install=(
                RiggingInstallStep(
                    method="mcp-server",
                    target="files",
                    command=("mcp-server-filesystem", "/app"),
                ),
            ),
        )

        reasons = unsupported_rigging_capability_reasons(
            _pi_runtime(), (adapter, server), {"pi-mcp-adapter": _adapter_capability()}
        )

        self.assertEqual(reasons, ())

    def test_gate_still_refuses_without_the_provider(self) -> None:
        reasons = unsupported_rigging_capability_reasons(
            _pi_runtime(), (_mcp_rigging(),), {}
        )

        self.assertEqual(len(reasons), 1)
        self.assertIn("mcp-server", reasons[0])

    def test_check_payload_names_the_provider(self) -> None:
        capabilities = {"pi-mcp-adapter": _adapter_capability()}

        payload = rigging_capabilities_to_json(
            _pi_runtime(), (_mcp_rigging(),), capabilities
        )

        mcp_checks = [
            check
            for check in payload["install_checks"]
            if check["method"] == "mcp-server"
        ]
        self.assertEqual(mcp_checks[0]["provided_by"], "pi-mcp-adapter")
        self.assertTrue(mcp_checks[0]["supported"])

    def test_claude_code_native_support_gains_no_provided_by(self) -> None:
        runtime = RuntimeRecipe(
            name="claude-runtime",
            backend="container",
            harness="claude-code",
            image="img",
            command=("claude",),
        )
        rigging = RiggingRecipe(
            name="files-mcp",
            install=(
                RiggingInstallStep(
                    method="mcp-server",
                    target="files",
                    command=("mcp-server-filesystem", "/app"),
                ),
            ),
        )

        payload = rigging_capabilities_to_json(runtime, (rigging,), {})

        check = payload["install_checks"][0]
        self.assertTrue(check["supported"])
        self.assertNotIn("provided_by", check)

    def test_harbor_agent_extension_supported_for_pi_only(self) -> None:
        step = RiggingInstallStep(
            method="agent-extension",
            target="npm:pi-mcp-adapter@2.15.0",
            agent="pi",
        )
        rigging = RiggingRecipe(name="adapter", install=(step,))
        pi_harbor = RuntimeRecipe(
            name="harbor-pi",
            backend="harbor",
            harness="pi",
            image="yacht/harbor-launcher:harbor-0.20.0",
            command=(),
        )
        claude_harbor = RuntimeRecipe(
            name="harbor-claude",
            backend="harbor",
            harness="claude-code",
            image="yacht/harbor-launcher:harbor-0.20.0",
            command=(),
        )
        claude_step = RiggingInstallStep(
            method="agent-extension", target="npm:x@1.0.0", agent="claude-code"
        )

        self.assertEqual(
            unsupported_rigging_capability_reasons(pi_harbor, (rigging,), {}), ()
        )
        self.assertEqual(
            len(
                unsupported_rigging_capability_reasons(
                    claude_harbor,
                    (RiggingRecipe(name="x", install=(claude_step,)),),
                    {},
                )
            ),
            1,
        )


# The shape a real pi-mcp-adapter session preserves: the observable
# tool is the mcp gateway, and the per-server evidence is the prefixed
# inner name carried in the gateway call's arguments (ADR 0024).
PI_JSONL = "\n".join(
    [
        '{"type": "agent_start"}',
        '{"type": "message_end", "message": {"role": "assistant", "api": "anthropic", "content": [{"type": "toolCall", "name": "mcp", "arguments": {"tool": "mcp__files_list_directory", "args": {"path": "/app"}}}]}}',
        '{"type": "turn_end", "toolResults": [{"toolName": "mcp"}]}',
        '{"type": "message_end", "message": {"role": "assistant", "api": "anthropic", "content": [{"type": "text", "text": "done"}]}}',
        '{"type": "agent_end"}',
    ]
)


class PiObservedToolCallTests(unittest.TestCase):
    def test_parses_gateway_inner_names_and_tool_results(self) -> None:
        self.assertEqual(
            tool_calls_from_pi_jsonl(PI_JSONL),
            ("mcp__files_list_directory", "mcp"),
        )

    def test_gateway_calls_without_an_inner_tool_yield_only_the_gateway(
        self,
    ) -> None:
        stream = "\n".join(
            [
                '{"type": "agent_start"}',
                '{"type": "message_end", "message": {"role": "assistant", "api": "anthropic", "content": [{"type": "toolCall", "name": "mcp", "arguments": {"server": "files"}}]}}',
                '{"type": "turn_end", "toolResults": [{"toolName": "mcp"}]}',
                '{"type": "agent_end"}',
            ]
        )

        self.assertEqual(tool_calls_from_pi_jsonl(stream), ("mcp",))

    def test_non_pi_output_is_unmeasured(self) -> None:
        self.assertIsNone(tool_calls_from_pi_jsonl("plain text output"))

    def test_observed_tool_calls_reads_preserved_pi_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            (trial_dir / "agent").mkdir()
            (trial_dir / "agent" / "pi.txt").write_text(PI_JSONL, encoding="utf-8")

            calls, source = _observed_tool_calls(trial_dir)

        self.assertEqual(calls, ["mcp__files_list_directory", "mcp"])
        self.assertEqual(source, PI_JSONL_EVIDENCE)

    def test_missing_pi_output_stays_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls, source = _observed_tool_calls(Path(tmp))

        self.assertEqual(calls, [])
        self.assertIsNone(source)

    def test_pi_stream_with_no_tool_calls_is_measured_empty(self) -> None:
        """A parseable pi stream that never called a tool is measured zero,
        distinct from no preserved stream at all (unmeasured)."""
        no_tools = "\n".join(
            [
                '{"type": "agent_start"}',
                '{"type": "message_end", "message": {"role": "assistant", "api": "anthropic", "content": [{"type": "text", "text": "done"}]}}',
                '{"type": "agent_end"}',
            ]
        )

        self.assertEqual(tool_calls_from_pi_jsonl(no_tools), ())

        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            (trial_dir / "agent").mkdir()
            (trial_dir / "agent" / "pi.txt").write_text(no_tools, encoding="utf-8")

            calls, source = _observed_tool_calls(trial_dir)

        self.assertEqual(calls, [])
        self.assertEqual(source, PI_JSONL_EVIDENCE)

    def test_pi_output_truncated_mid_multibyte_char_is_unmeasured(self) -> None:
        """A pi.txt truncated mid-multibyte character (e.g. by a killed tee)
        must not crash the run; it should degrade to unmeasured, matching
        the sibling evidence sources' handling of unreadable files."""
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            (trial_dir / "agent").mkdir()
            (trial_dir / "agent" / "pi.txt").write_bytes(
                b'{"type": "agent_start"}\n\xe2\x9c'
            )

            calls, source = _observed_tool_calls(trial_dir)

        self.assertEqual(calls, [])
        self.assertIsNone(source)


if __name__ == "__main__":
    unittest.main()
