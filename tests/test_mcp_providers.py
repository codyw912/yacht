import unittest

from yacht.config.loader import _parse_tool_capabilities
from yacht.runtimes.tool_capabilities import ProvidedInstall, ToolCapability


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


if __name__ == "__main__":
    unittest.main()
