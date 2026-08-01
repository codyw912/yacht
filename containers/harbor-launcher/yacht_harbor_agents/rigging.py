"""Shell commands that apply yacht rigging steps inside a task container.

This module is imported by the yacht agent classes inside the launcher
image and by yacht's test suite; it must not import harbor.
"""

from __future__ import annotations

import base64
import posixpath
import shlex
from typing import Any


SUPPORTED_METHODS = ("agent-extension", "config-file", "package")

_AGENT_EXTENSION_INSTALLERS = {
    # pi's node comes from nvm inside harbor task containers.
    "pi": ". ~/.nvm/nvm.sh; pi install {target}",
}


def rigging_commands(steps: list[dict[str, Any]]) -> list[str]:
    return [_step_command(step) for step in steps]


def _step_command(step: dict[str, Any]) -> str:
    method = step.get("method")
    if method == "package":
        return _package_command(step)
    if method == "config-file":
        return _config_file_command(step)
    if method == "agent-extension":
        return _agent_extension_command(step)
    supported = ", ".join(SUPPORTED_METHODS)
    raise ValueError(
        f"rigging step method {method!r} is not supported in task containers; "
        f"supported methods: {supported}"
    )


def _agent_extension_command(step: dict[str, Any]) -> str:
    agent = step.get("agent")
    template = _AGENT_EXTENSION_INSTALLERS.get(agent)
    if template is None:
        supported = ", ".join(sorted(_AGENT_EXTENSION_INSTALLERS))
        raise ValueError(
            f"agent-extension steps are supported for agents {supported} in "
            f"task containers, got {agent!r}"
        )
    target = step.get("target")
    if not isinstance(target, str) or not target.startswith("npm:"):
        raise ValueError(
            f"agent-extension step target must use the npm: prefix, got {target!r}"
        )
    return template.format(target=shlex.quote(target))


def _package_command(step: dict[str, Any]) -> str:
    target = step.get("target")
    if not isinstance(target, str) or not target.startswith("npm:"):
        raise ValueError(
            f"package step target must use the npm: prefix, got {target!r}"
        )
    package = target.removeprefix("npm:")
    if not package:
        raise ValueError("package step target must name a package")
    return f"npm install -g {shlex.quote(package)}"


def _config_file_command(step: dict[str, Any]) -> str:
    target = step.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError("config-file step requires a target path")
    if posixpath.isabs(target) or ".." in target.split("/"):
        raise ValueError(
            f"config-file step target must be a relative path inside the "
            f"container home, got {target!r}"
        )
    content = step.get("content")
    if not isinstance(content, str):
        raise ValueError("config-file step requires string content")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    quoted_target = shlex.quote(target)
    return (
        f'mkdir -p "$(dirname "$HOME"/{quoted_target})" && '
        f"printf '%s' {shlex.quote(encoded)} | base64 -d > "
        f'"$HOME"/{quoted_target}'
    )
