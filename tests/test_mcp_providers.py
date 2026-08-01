import json
import unittest

from yacht.config.loader import _parse_tool_capabilities
from yacht.contracts.schemas import SchemaValidationError, _validate_tool_capabilities
from yacht.domain.model import RiggingInstallStep, RiggingRecipe
from yacht.harnesses.mcp_config import (
    MCP_INSTALL_PROVIDERS,
    McpConfigError,
    render_provider_mcp_config,
    supported_mcp_install_provider,
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


if __name__ == "__main__":
    unittest.main()
