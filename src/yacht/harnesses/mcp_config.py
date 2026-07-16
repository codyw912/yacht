"""Harness-specific rendering of mcp-server install steps.

This is the harness adapter hook from ADR 0008: a harness that loads MCP
servers from configuration registers a renderer here, turning mcp-server
install steps into a config-file write inside the trial home. Harnesses
without a renderer keep blocking the method before tokens are spent.

This module stays free of imports from yacht.runtimes so the setup and
capability machinery there can depend on it without an import cycle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from yacht.domain.model import RiggingInstallStep


class McpConfigError(ValueError):
    """Raised when mcp-server install steps cannot be rendered."""


@dataclass(frozen=True)
class McpServerEntry:
    origin_name: str
    server_name: str


@dataclass(frozen=True)
class McpConfigRender:
    target: str
    content: str
    entries: tuple[McpServerEntry, ...]


CLAUDE_CODE_MCP_CONFIG_TARGET = ".claude.json"


def supports_mcp_server_installs(harness: str | None) -> bool:
    return harness in _MCP_CONFIG_RENDERERS


def render_mcp_config(
    harness: str | None,
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> McpConfigRender | None:
    """Render (rigging name, step) pairs into one harness config file.

    Returns None when the harness has no renderer; raises McpConfigError
    when it has one but the steps cannot be rendered.
    """
    if harness is None:
        return None
    renderer = _MCP_CONFIG_RENDERERS.get(harness)
    if renderer is None:
        return None
    return renderer(steps)


def _render_claude_code_mcp_config(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> McpConfigRender:
    servers: dict[str, dict[str, object]] = {}
    entries: list[McpServerEntry] = []
    for origin_name, step in steps:
        if not step.command:
            raise McpConfigError(f"mcp-server install {step.target} requires command")
        if step.target in servers:
            raise McpConfigError(
                f"mcp-server install declares duplicate server name {step.target}"
            )
        servers[step.target] = {
            "command": step.command[0],
            "args": list(step.command[1:]),
        }
        entries.append(McpServerEntry(origin_name=origin_name, server_name=step.target))
    return McpConfigRender(
        target=CLAUDE_CODE_MCP_CONFIG_TARGET,
        content=json.dumps({"mcpServers": servers}, indent=2, sort_keys=True) + "\n",
        entries=tuple(entries),
    )


_MCP_CONFIG_RENDERERS = {
    "claude-code": _render_claude_code_mcp_config,
}
