"""Shared display formatting for collapsed provenance blocks."""

from __future__ import annotations

from typing import Any


def provenance_harness_label(provenance: dict[str, Any]) -> str:
    harness = _section(provenance, "harness")
    name = harness.get("name")
    version = harness.get("version")
    if not name:
        return "mixed" if "harness.name" in provenance_mixed(provenance) else "unknown"
    if version:
        return f"{name} {version}"
    return str(name)


def provenance_model_label(provenance: dict[str, Any]) -> str:
    model = _section(provenance, "model")
    configured = model.get("configured")
    resolved = model.get("resolved")
    if not configured:
        return (
            "mixed" if "model.configured" in provenance_mixed(provenance) else "unknown"
        )
    if resolved and resolved != configured:
        return f"{configured} ({resolved})"
    return str(configured)


def provenance_tools_label(provenance: dict[str, Any]) -> str:
    tools = provenance.get("tools")
    if tools is None:
        return "mixed" if "tools" in provenance_mixed(provenance) else "unknown"
    if not tools:
        return "none"
    return ", ".join(_tool_label(tool) for tool in tools)


def provenance_mixed(provenance: dict[str, Any]) -> list[str]:
    mixed = provenance.get("mixed")
    if not isinstance(mixed, list):
        return []
    return [str(item) for item in mixed]


def _tool_label(tool: Any) -> str:
    if not isinstance(tool, dict):
        return str(tool)
    name = str(tool.get("name") or "unknown")
    version = tool.get("version")
    if version:
        return f"{name}@{version}"
    return name


def _section(provenance: dict[str, Any], key: str) -> dict[str, Any]:
    value = provenance.get(key)
    if isinstance(value, dict):
        return value
    return {}
