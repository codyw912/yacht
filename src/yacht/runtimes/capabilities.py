from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from yacht.domain.model import RiggingInstallStep, RiggingRecipe, RuntimeRecipe
from yacht.harnesses.mcp_config import McpInstallProvider, supports_mcp_server_installs
from yacht.harnesses.skill_config import supports_skill_installs
from yacht.reports.surface_metadata import harness_for_runtime
from yacht.runtimes.tool_capabilities import (
    ToolCapability,
    provided_mcp_install_provider,
    tool_capabilities_to_json,
)


SUPPORTED_INSTALL_METHODS_BY_BACKEND: dict[str, tuple[str, ...]] = {
    "container": (
        "agent-extension",
        "config-file",
        "mcp-server",
        "package",
        "preinstalled",
        "custom-command",
        "skill",
    ),
    "harbor": (
        "agent-extension",
        "config-file",
        "mcp-server",
        "package",
        "skill",
    ),
    "host-nix": (
        "agent-extension",
        "config-file",
        "mcp-server",
        "package",
        "preinstalled",
        "custom-command",
        "skill",
    ),
}

HARBOR_AGENT_EXTENSION_HARNESSES = {"pi"}

SUPPORTED_PACKAGE_TARGET_PREFIXES = ("npm:",)


def rigging_capabilities_to_json(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    tool_capabilities: dict[str, ToolCapability] | None = None,
) -> dict[str, Any]:
    checks = _install_checks(runtime, riggings, tool_capabilities)
    unsupported = [check for check in checks if not bool(check["supported"])]
    payload = {
        "status": "unsupported" if unsupported else "supported",
        "runtime_backend": runtime.backend,
        "runtime_harness": harness_for_runtime(runtime),
        "runtime_agent": harness_for_runtime(runtime),
        "supported_install_methods": list(_supported_methods(runtime)),
        "install_checks": checks,
    }
    if tool_capabilities is not None:
        payload["tools"] = tool_capabilities_to_json(
            tuple(tool for rigging in riggings for tool in rigging.tools),
            tool_capabilities,
        )
    return payload


def unsupported_rigging_capability_reasons(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    tool_capabilities: dict[str, ToolCapability] | None = None,
) -> tuple[str, ...]:
    checks = _install_checks(runtime, riggings, tool_capabilities)
    return tuple(
        str(check["reason"])
        for check in checks
        if not bool(check["supported"]) and "reason" in check
    )


def _install_checks(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    tool_capabilities: dict[str, ToolCapability] | None,
) -> list[dict[str, Any]]:
    provider = provided_mcp_install_provider(
        harness_for_runtime(runtime), riggings, tool_capabilities
    )
    return [
        _install_check(runtime, rigging, step, provider)
        for rigging in riggings
        for step in rigging.install
    ]


def _install_check(
    runtime: RuntimeRecipe,
    rigging: RiggingRecipe,
    step: RiggingInstallStep,
    provider: McpInstallProvider | None,
) -> dict[str, Any]:
    supported, reason = _step_support(runtime, step, provider)
    payload = {
        "origin": "rigging",
        "origin_name": rigging.name,
        "method": step.method,
        "target": step.target,
        "supported": supported,
    }
    if reason is not None:
        payload["reason"] = reason
    if (
        step.method == "mcp-server"
        and supported
        and not supports_mcp_server_installs(harness_for_runtime(runtime))
        and provider is not None
    ):
        payload["provided_by"] = provider.tool_name
    return payload


def _step_support(
    runtime: RuntimeRecipe,
    step: RiggingInstallStep,
    provider: McpInstallProvider | None,
) -> tuple[bool, str | None]:
    supported_methods = _supported_methods(runtime)
    if step.method not in supported_methods:
        return (
            False,
            "runtime backend "
            f"{runtime.backend} does not support rigging install method "
            f"{step.method} yet",
        )
    if step.method == "agent-extension":
        runtime_harness = harness_for_runtime(runtime)
        if runtime_harness is None:
            return (
                False,
                "agent-extension install requires runtime harness metadata",
            )
        if step.agent is not None and step.agent != runtime_harness:
            return (
                False,
                "agent-extension install targets agent "
                f"{step.agent}, but runtime harness is {runtime_harness}",
            )
        if (
            runtime.backend == "harbor"
            and runtime_harness not in HARBOR_AGENT_EXTENSION_HARNESSES
        ):
            return (
                False,
                "agent-extension installs on the harbor backend are supported "
                f"for harnesses {sorted(HARBOR_AGENT_EXTENSION_HARNESSES)} only, "
                f"not {runtime_harness}",
            )
    if step.method == "mcp-server":
        runtime_harness = harness_for_runtime(runtime)
        if not supports_mcp_server_installs(runtime_harness) and provider is None:
            return (
                False,
                f"runtime harness {runtime_harness} does not support rigging "
                "install method mcp-server and no rigged tool provides it",
            )
        if not step.command:
            return (
                False,
                f"mcp-server install {step.target} requires command",
            )
    if step.method == "package" and not step.target.startswith(
        SUPPORTED_PACKAGE_TARGET_PREFIXES
    ):
        return (
            False,
            f"package install target {step.target} is not supported yet; "
            "supported prefixes: " + ", ".join(SUPPORTED_PACKAGE_TARGET_PREFIXES),
        )
    if step.method == "config-file":
        target_path = _relative_target_path(step.target)
        if target_path is None:
            return (
                False,
                f"config-file install target {step.target} must be a relative "
                "path inside the trial home without traversal",
            )
    if step.method == "skill":
        runtime_harness = harness_for_runtime(runtime)
        if not supports_skill_installs(runtime_harness):
            return (
                False,
                f"runtime harness {runtime_harness} does not support "
                "rigging install method skill",
            )
        if "/" in step.target or step.target in {".", ".."}:
            return (
                False,
                f"skill install target {step.target} must be a skill name, not a path",
            )
        if step.content is None:
            return (
                False,
                f"skill install {step.target} requires content",
            )
    return True, None


def _relative_target_path(target: str) -> str | None:
    path = PurePosixPath(target)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    return str(path)


def _supported_methods(runtime: RuntimeRecipe) -> tuple[str, ...]:
    return SUPPORTED_INSTALL_METHODS_BY_BACKEND.get(runtime.backend, ())
