from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yacht.preflight import AgentPromptResult, AgentPromptRunner
from yacht.regatta import RuntimeInstance


class PiAdapterNotConfigured(ValueError):
    """Raised when Pi prompt execution is requested without a launcher."""


@dataclass(frozen=True)
class PiPromptRequest:
    prompt: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    transcript_path: Path


PiPromptLauncher = Callable[[PiPromptRequest], AgentPromptResult]


class PiAdapter:
    def __init__(self, launcher: PiPromptLauncher | None = None) -> None:
        self._launcher = launcher

    def agent_prompt_runner(
        self,
        *,
        instance: RuntimeInstance,
        transcript_dir: Path,
    ) -> AgentPromptRunner:
        def run(prompt: str, env: dict[str, str], cwd: Path) -> AgentPromptResult:
            return self.run_headless_prompt(
                prompt=prompt,
                instance=instance,
                env=env,
                cwd=cwd,
                transcript_path=transcript_dir / "pi-headless-prompt.json",
            )

        return run

    def run_headless_prompt(
        self,
        *,
        prompt: str,
        instance: RuntimeInstance,
        env: dict[str, str],
        cwd: Path,
        transcript_path: Path,
    ) -> AgentPromptResult:
        if self._launcher is None:
            raise PiAdapterNotConfigured(
                "Pi headless prompt launcher is not configured"
            )

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        request = PiPromptRequest(
            prompt=prompt,
            argv=instance.command_prefix + instance.runtime.command,
            env=env,
            cwd=cwd,
            transcript_path=transcript_path,
        )
        return self._launcher(request)
