from __future__ import annotations

from typing import Any

from yacht.regatta import RiggingInstallStep, RiggingRecipe, RuntimeRecipe
from yacht.surface_metadata import agent_for_runtime


SUPPORTED_INSTALL_METHODS_BY_BACKEND: dict[str, tuple[str, ...]] = {
    "container": ("agent-extension", "preinstalled"),
    "host-nix": ("agent-extension", "preinstalled"),
}


def rigging_capabilities_to_json(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> dict[str, Any]:
    checks = _install_checks(runtime, riggings)
    unsupported = [check for check in checks if not bool(check["supported"])]
    return {
        "status": "unsupported" if unsupported else "supported",
        "runtime_backend": runtime.backend,
        "runtime_agent": agent_for_runtime(runtime),
        "supported_install_methods": list(_supported_methods(runtime)),
        "install_checks": checks,
    }


def unsupported_rigging_capability_reasons(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    checks = _install_checks(runtime, riggings)
    return tuple(
        str(check["reason"])
        for check in checks
        if not bool(check["supported"]) and "reason" in check
    )


def _install_checks(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> list[dict[str, Any]]:
    return [
        _install_check(runtime, rigging, step)
        for rigging in riggings
        for step in rigging.install
    ]


def _install_check(
    runtime: RuntimeRecipe,
    rigging: RiggingRecipe,
    step: RiggingInstallStep,
) -> dict[str, Any]:
    supported, reason = _step_support(runtime, step)
    payload = {
        "origin": "rigging",
        "origin_name": rigging.name,
        "method": step.method,
        "target": step.target,
        "supported": supported,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def _step_support(
    runtime: RuntimeRecipe,
    step: RiggingInstallStep,
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
        runtime_agent = agent_for_runtime(runtime)
        if runtime_agent is None:
            return (
                False,
                "agent-extension install requires runtime agent metadata",
            )
        if step.agent is not None and step.agent != runtime_agent:
            return (
                False,
                "agent-extension install targets agent "
                f"{step.agent}, but runtime agent is {runtime_agent}",
            )
    return True, None


def _supported_methods(runtime: RuntimeRecipe) -> tuple[str, ...]:
    return SUPPORTED_INSTALL_METHODS_BY_BACKEND.get(runtime.backend, ())
