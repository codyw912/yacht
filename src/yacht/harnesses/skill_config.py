"""Harness-specific rendering of skill install steps.

A logical `skill` install names the skill and carries its content. Each
first-class adapter that supports skills registers a renderer here that
turns those steps into native project-scoped files. Harnesses without a
renderer keep blocking the method before tokens are spent.

This module stays free of imports from yacht.runtimes so the setup and
capability machinery there can depend on it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yacht.domain.model import RiggingInstallStep


class SkillConfigError(ValueError):
    """Raised when skill install steps cannot be rendered."""


@dataclass(frozen=True)
class SkillInstallRender:
    origin_name: str
    skill_name: str
    target: str
    content: str


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
            f"runtime harness {harness} does not support rigging "
            "install method skill"
        )
    return _SKILL_INSTALL_RENDERERS[harness](steps)


def _render_claude_code_skill_installs(
    steps: tuple[tuple[str, RiggingInstallStep], ...],
) -> tuple[SkillInstallRender, ...]:
    renders: list[SkillInstallRender] = []
    for origin_name, step in steps:
        if step.content is None:
            raise SkillConfigError(
                f"skill install {step.target} is missing content"
            )
        renders.append(
            SkillInstallRender(
                origin_name=origin_name,
                skill_name=step.target,
                target=f".claude/skills/{step.target}/SKILL.md",
                content=step.content,
            )
        )
    return tuple(renders)


_SKILL_INSTALL_RENDERERS = {
    "claude-code": _render_claude_code_skill_installs,
}
