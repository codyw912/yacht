"""Yacht-owned Harbor agents (ADR 0012).

These classes reuse Harbor's installed-agent implementations for the
harness install and run phases, and additionally apply yacht rigging
steps inside the task container so the tools under test are provisioned
by yacht's own step model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment

from yacht_harbor_agents.rigging import rigging_commands


class RiggingStepError(RuntimeError):
    pass


async def apply_rigging_steps(
    environment: BaseEnvironment,
    steps: list[dict[str, Any]],
) -> None:
    for command in rigging_commands(steps):
        result = await environment.exec(command=command)
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RiggingStepError(
                f"rigging step failed with exit code {result.return_code}: "
                f"{command}\n{detail}"
            )


class YachtClaudeCode(ClaudeCode):
    @staticmethod
    def name() -> str:
        return "yacht-claude-code"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        super().__init__(logs_dir, *args, **kwargs)

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await apply_rigging_steps(environment, self._rigging_steps)


class YachtPi(Pi):
    @staticmethod
    def name() -> str:
        return "yacht-pi"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        super().__init__(logs_dir, *args, **kwargs)

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await apply_rigging_steps(environment, self._rigging_steps)
