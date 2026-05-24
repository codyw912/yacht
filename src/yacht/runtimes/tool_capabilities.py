from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCapability:
    name: str
    kind: str
    description: str = ""
    interfaces: tuple[str, ...] = ()
    install_methods: tuple[str, ...] = ()
    expected_tool_calls: tuple[str, ...] = ()

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


def tool_capabilities_to_json(
    tool_names: tuple[str, ...],
    capabilities: dict[str, ToolCapability],
) -> list[dict[str, Any]]:
    return [
        capabilities[name].to_json()
        for name in sorted(dict.fromkeys(tool_names))
        if name in capabilities
    ]
