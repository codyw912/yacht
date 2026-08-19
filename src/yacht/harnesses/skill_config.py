"""Harness-specific rendering of skill install steps.

A logical `skill` install names the skill and carries its content. Each
first-class adapter that supports skills registers a renderer here that
turns those steps into native project-scoped files. Harnesses without a
renderer keep blocking the method before tokens are spent.

This module stays free of imports from yacht.runtimes so the setup and
capability machinery there can depend on it without an import cycle.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yacht.domain.model import RiggingInstallStep


class SkillConfigError(ValueError):
    """Raised when skill install steps cannot be rendered."""


#: The skill body's filename inside the skill directory. A resource may
#: not claim it: the host writer emits the body first and the Harbor
#: lowering emits it last, so a collision would produce two different
#: trees from one payload digest.
SKILL_BODY_FILENAME = "SKILL.md"


@dataclass(frozen=True)
class SkillResourceRender:
    target: str
    content: str


@dataclass(frozen=True)
class SkillInstallRender:
    origin_name: str
    skill_name: str
    target: str
    content: str
    resources: tuple[SkillResourceRender, ...]
    content_digest: str


def normalized_resource_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Canonical relative paths inside a skill directory.

    Normalizing before rendering and hashing is what keeps the payload
    digest honest: `a/b` and `./a/b` are one file, so they must not hash
    as two entries or write twice in an order-dependent way.
    """
    normalized: list[str] = []
    seen: dict[str, str] = {}
    for path in paths:
        canonical = _normalized_resource_path(path)
        if canonical in seen:
            raise SkillConfigError(
                f"skill install resource {path} and {seen[canonical]} both "
                f"name {canonical}"
            )
        seen[canonical] = path
        normalized.append(canonical)
    return tuple(normalized)


def _normalized_resource_path(path: str) -> str:
    if not path or path.startswith("/"):
        raise SkillConfigError(f"skill install resource path {path!r} must be relative")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise SkillConfigError(
            f"skill install resource path {path!r} must be relative without '..'"
        )
    parts = [part for part in pure.parts if part != "."]
    if not parts:
        raise SkillConfigError(f"skill install resource path {path!r} names no file")
    canonical = "/".join(parts)
    if canonical == SKILL_BODY_FILENAME:
        raise SkillConfigError(
            f"skill install resource path {path!r} is reserved for the "
            "skill body; give the resource its own name"
        )
    return canonical


def supports_skill_installs(harness: str | None) -> bool:
    return harness in _SKILL_INSTALL_RENDERERS


def render_skill_installs(
    harness: str | None,
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> tuple[SkillInstallRender, ...]:
    """Render (rigging name, step) pairs into native skill files.

    Raises SkillConfigError when the harness has no renderer or the
    steps cannot be rendered. Callers that only need a capability
    check should use supports_skill_installs.
    """
    if harness is None or harness not in _SKILL_INSTALL_RENDERERS:
        raise SkillConfigError(
            f"runtime harness {harness} does not support rigging install method skill"
        )
    return _SKILL_INSTALL_RENDERERS[harness](steps)


def _render_skill_installs(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
    base_directory: str,
) -> tuple[SkillInstallRender, ...]:
    renders: list[SkillInstallRender] = []
    for origin_name, step in steps:
        if step.content is None:
            raise SkillConfigError(f"skill install {step.target} is missing content")
        skill_directory = f"{base_directory}/{step.target}"
        paths = normalized_resource_paths(
            tuple(resource.path for resource in step.resources)
        )
        payload = [(SKILL_BODY_FILENAME, step.content)] + [
            (path, resource.content)
            for path, resource in zip(paths, step.resources, strict=True)
        ]
        renders.append(
            SkillInstallRender(
                origin_name=origin_name,
                skill_name=step.target,
                target=f"{skill_directory}/{SKILL_BODY_FILENAME}",
                content=step.content,
                resources=tuple(
                    SkillResourceRender(
                        target=f"{skill_directory}/{path}",
                        content=content,
                    )
                    for path, content in payload[1:]
                ),
                content_digest=_payload_digest(payload),
            )
        )
    return tuple(renders)


def _payload_digest(payload: list[tuple[str, str]]) -> str:
    """sha256 over the logical bundle: sorted canonical path, then content.

    Keyed on paths within the skill directory, not the rendered targets, so
    one skill has one digest whichever harness layout it lands in.
    """
    digest = hashlib.sha256()
    for relative_path, content in sorted(payload):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(content.encode("utf-8"))
        digest.update(b"\x00")
    return f"sha256:{digest.hexdigest()}"


def _render_claude_code_skill_installs(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> tuple[SkillInstallRender, ...]:
    return _render_skill_installs(steps, ".claude/skills")


def _render_agent_skills_installs(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> tuple[SkillInstallRender, ...]:
    return _render_skill_installs(steps, ".agents/skills")


_SKILL_INSTALL_RENDERERS = {
    "claude-code": _render_claude_code_skill_installs,
    "codex": _render_agent_skills_installs,
    "omp": _render_agent_skills_installs,
}
