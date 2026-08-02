"""Harness-specific rendering of mcp-server install steps.

This is the harness adapter hook from ADR 0008: a harness that loads MCP
servers from configuration registers a renderer here, turning mcp-server
install steps into a config-file write inside the trial home. Harnesses
without a renderer keep blocking the method before tokens are spent.
Providers registered here can also supply the renderer for a harness
that lacks one of its own (ADR 0024).

This module stays free of imports from yacht.runtimes so the setup and
capability machinery there can depend on it without an import cycle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

# Deferred to type-checking only: contracts.schemas and
# runtimes.tool_capabilities both need to import this module at runtime,
# and domain.model imports contracts.schemas, so a runtime import here
# would close an import cycle. RiggingInstallStep is only ever used in
# annotations below (deferred by `from __future__ import annotations`).
if TYPE_CHECKING:
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


def _mcp_servers_from_steps(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> tuple[dict[str, dict[str, object]], tuple[McpServerEntry, ...]]:
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
    return servers, tuple(entries)


def _render_claude_code_mcp_config(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> McpConfigRender:
    servers, entries = _mcp_servers_from_steps(steps)
    return McpConfigRender(
        target=CLAUDE_CODE_MCP_CONFIG_TARGET,
        content=json.dumps({"mcpServers": servers}, indent=2, sort_keys=True) + "\n",
        entries=entries,
    )


_MCP_CONFIG_RENDERERS = {
    "claude-code": _render_claude_code_mcp_config,
}


PI_MCP_ADAPTER_CONFIG_TARGET = ".pi/agent/mcp.json"


@dataclass(frozen=True)
class McpInstallProvider:
    """A rigged tool yacht knows how to render MCP configuration for.

    pins_namespace records whether the rendered settings guarantee a
    per-server tool-name convention delivery matching can key on;
    namespace_format is that convention, with {server} standing for the
    sanitized server name. A provider without the guarantee yields no
    delivery expectation.
    """

    tool_name: str
    harness: str
    config_target: str
    pins_namespace: bool
    namespace_format: str


MCP_INSTALL_PROVIDERS: dict[tuple[str, str], McpInstallProvider] = {
    ("pi-mcp-adapter", "pi"): McpInstallProvider(
        tool_name="pi-mcp-adapter",
        harness="pi",
        config_target=PI_MCP_ADAPTER_CONFIG_TARGET,
        pins_namespace=True,
        # The adapter's "mcp" toolPrefix names tools
        # mcp__<server>_<tool> — a single underscore before the tool,
        # not Claude Code's mcp__<server>__<tool> convention. Verified
        # against pi-mcp-adapter 2.17.0's formatToolName.
        namespace_format="mcp__{server}_",
    ),
}


def supported_mcp_install_provider(tool_name: str, harness: str) -> bool:
    return (tool_name, harness) in MCP_INSTALL_PROVIDERS


def provider_mcp_namespace(provider: McpInstallProvider, server: str) -> str:
    """The namespace marker a provider guarantees for one server's tools.

    Server names are sanitized the way pi-mcp-adapter sanitizes them:
    hyphens become underscores before the name enters a tool name.
    """
    return provider.namespace_format.format(server=server.replace("-", "_"))


def render_provider_mcp_config(
    provider: McpInstallProvider,
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> McpConfigRender:
    servers, entries = _mcp_servers_from_steps(steps)
    content = (
        json.dumps(
            {
                "mcpServers": servers,
                # The mcp toolPrefix pins the namespace_format naming
                # for every route to a server's tools — direct
                # registration and the gateway's inner names alike.
                "settings": {"directTools": True, "toolPrefix": "mcp"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return McpConfigRender(
        target=provider.config_target,
        content=content,
        entries=entries,
    )
