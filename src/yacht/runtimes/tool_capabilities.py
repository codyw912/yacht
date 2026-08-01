from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yacht.harnesses.mcp_config import MCP_INSTALL_PROVIDERS, McpInstallProvider

# Deferred to type-checking only: domain.model imports contracts.schemas,
# which imports this module for BUILT_IN_TOOL_CAPABILITIES, so a runtime
# import of domain.model here would close an import cycle. RiggingRecipe
# is only ever used in an annotation below (deferred by `from __future__
# import annotations`).
if TYPE_CHECKING:
    from yacht.domain.model import RiggingRecipe


@dataclass(frozen=True)
class ProvidedInstall:
    method: str
    harness: str


@dataclass(frozen=True)
class ToolCapability:
    name: str
    kind: str
    description: str = ""
    interfaces: tuple[str, ...] = ()
    install_methods: tuple[str, ...] = ()
    expected_tool_calls: tuple[str, ...] = ()
    provides: tuple[ProvidedInstall, ...] = ()

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
        }
        if self.description:
            payload["description"] = self.description
        if self.interfaces:
            payload["interfaces"] = list(self.interfaces)
        if self.install_methods:
            payload["install_methods"] = list(self.install_methods)
        if self.expected_tool_calls:
            payload["expected_tool_calls"] = list(self.expected_tool_calls)
        if self.provides:
            payload["provides"] = [
                {"method": provided.method, "harness": provided.harness}
                for provided in self.provides
            ]
        return payload


BUILT_IN_TOOL_CAPABILITIES: dict[str, ToolCapability] = {
    "fff": ToolCapability(
        name="fff",
        kind="code-navigation",
        description="Codebase memory and navigation tool.",
        interfaces=("agent-tool",),
        install_methods=("agent-extension",),
        expected_tool_calls=("fffind", "ffgrep"),
    ),
    "local-smoke": ToolCapability(
        name="local-smoke",
        kind="test-fixture",
        description="Local smoke tool fixture used by YACHT examples and tests.",
        interfaces=("agent-tool",),
        install_methods=("preinstalled",),
        expected_tool_calls=("local-smoke",),
    ),
}


def provided_mcp_install_provider(
    harness: str | None,
    riggings: tuple[RiggingRecipe, ...],
    capabilities: dict[str, ToolCapability] | None,
) -> McpInstallProvider | None:
    """The supported provider a rigged tool declares for this harness,
    or None. Declaration and registry must agree: a tool that declares
    provision yacht cannot render for resolves to nothing."""
    if harness is None or not capabilities:
        return None
    for rigging in riggings:
        for tool_name in rigging.tools:
            capability = capabilities.get(tool_name)
            if capability is None:
                continue
            for provided in capability.provides:
                if provided.method != "mcp-server" or provided.harness != harness:
                    continue
                provider = MCP_INSTALL_PROVIDERS.get((tool_name, harness))
                if provider is not None:
                    return provider
    return None


def tool_capabilities_to_json(
    tool_names: tuple[str, ...],
    capabilities: dict[str, ToolCapability],
) -> list[dict[str, Any]]:
    return [
        capabilities[name].to_json()
        for name in sorted(dict.fromkeys(tool_names))
        if name in capabilities
    ]
