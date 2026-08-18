from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from yacht.harnesses.claude_code import (
    ClaudeCodeAdapter,
    SubprocessClaudeCodePromptLauncher,
    SubprocessClaudeCodeTaskLauncher,
)
from yacht.harnesses.codex import (
    CodexAdapter,
    SubprocessCodexPromptLauncher,
    SubprocessCodexTaskLauncher,
)
from yacht.harnesses.local_smoke import LocalSmokeAgentAdapter
from yacht.harnesses.omp import (
    OmpAdapter,
    SubprocessOmpPromptLauncher,
    SubprocessOmpTaskLauncher,
)
from yacht.harnesses.pi import (
    PiAdapter,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
)
from yacht.preflight import AgentPromptRunner
from yacht.domain.model import ConfigError
from yacht.domain.model import HarnessDeclaration
from yacht.domain.model import RuntimeInstance
from yacht.domain.model import Task
from yacht.workflows.task_attempts import AgentTaskResult


AgentPromptRunnerFactory = Callable[[RuntimeInstance, Path], AgentPromptRunner]


class TaskAgent(Protocol):
    def run_task(
        self,
        *,
        instance: RuntimeInstance,
        task: Task,
        prompt: str,
        env: dict[str, str],
        cwd: Path,
        transcript_path: Path,
    ) -> AgentTaskResult: ...


class HarnessAdapter(Protocol):
    name: str

    def agent_prompt_runner_factory(self) -> AgentPromptRunnerFactory: ...

    def task_agent(self) -> TaskAgent: ...


@dataclass(frozen=True)
class RegisteredHarnessAdapter:
    name: str
    _agent_prompt_runner_factory: Callable[[], AgentPromptRunnerFactory]
    _task_agent: Callable[[], TaskAgent]

    def agent_prompt_runner_factory(self) -> AgentPromptRunnerFactory:
        return self._agent_prompt_runner_factory()

    def task_agent(self) -> TaskAgent:
        return self._task_agent()


HarnessDeclarations = Mapping[str, HarnessDeclaration]


def harness_adapter(
    name: str,
    declarations: HarnessDeclarations | None = None,
) -> HarnessAdapter:
    adapter = _HARNESS_ADAPTERS.get(name)
    if adapter is not None:
        return adapter
    declaration = (declarations or {}).get(name)
    if declaration is not None:
        return _declared_adapter(declaration)
    raise ConfigError(f"unsupported harness adapter {name}")


def supported_harness_names() -> tuple[str, ...]:
    return tuple(sorted(_HARNESS_ADAPTERS))


def supported_agent_preflight_names() -> tuple[str, ...]:
    return ("none", *supported_harness_names())


def supported_task_attempt_names() -> tuple[str, ...]:
    return supported_harness_names()


def agent_prompt_runner_factory(
    name: str,
    declarations: HarnessDeclarations | None = None,
) -> AgentPromptRunnerFactory | None:
    if name == "none":
        return None
    try:
        adapter = harness_adapter(name, declarations)
    except ConfigError as error:
        raise ConfigError(f"unsupported agent preflight adapter {name}") from error
    return adapter.agent_prompt_runner_factory()


def task_agent(
    name: str,
    declarations: HarnessDeclarations | None = None,
) -> TaskAgent:
    try:
        adapter = harness_adapter(name, declarations)
    except ConfigError as error:
        raise ConfigError(f"unsupported task attempt agent {name}") from error
    return adapter.task_agent()


def _declared_adapter(declaration: HarnessDeclaration) -> HarnessAdapter:
    from yacht.harnesses.declared import DeclaredHarnessAdapter

    def prompt_runner_factory() -> AgentPromptRunnerFactory:
        adapter = DeclaredHarnessAdapter(declaration)
        return lambda instance, transcript_dir: adapter.agent_prompt_runner(
            instance=instance,
            transcript_dir=transcript_dir,
        )

    return RegisteredHarnessAdapter(
        name=declaration.name,
        _agent_prompt_runner_factory=prompt_runner_factory,
        _task_agent=lambda: DeclaredHarnessAdapter(declaration),
    )


def _pi_prompt_runner_factory() -> AgentPromptRunnerFactory:
    adapter = PiAdapter(launcher=SubprocessPiPromptLauncher())
    return lambda instance, transcript_dir: adapter.agent_prompt_runner(
        instance=instance,
        transcript_dir=transcript_dir,
    )


def _pi_task_agent() -> TaskAgent:
    return PiAdapter(task_launcher=SubprocessPiTaskLauncher())


def _claude_code_prompt_runner_factory() -> AgentPromptRunnerFactory:
    adapter = ClaudeCodeAdapter(launcher=SubprocessClaudeCodePromptLauncher())
    return lambda instance, transcript_dir: adapter.agent_prompt_runner(
        instance=instance,
        transcript_dir=transcript_dir,
    )


def _claude_code_task_agent() -> TaskAgent:
    return ClaudeCodeAdapter(task_launcher=SubprocessClaudeCodeTaskLauncher())


def _codex_prompt_runner_factory() -> AgentPromptRunnerFactory:
    adapter = CodexAdapter(launcher=SubprocessCodexPromptLauncher())
    return lambda instance, transcript_dir: adapter.agent_prompt_runner(
        instance=instance,
        transcript_dir=transcript_dir,
    )


def _codex_task_agent() -> TaskAgent:
    return CodexAdapter(task_launcher=SubprocessCodexTaskLauncher())


def _omp_prompt_runner_factory() -> AgentPromptRunnerFactory:
    adapter = OmpAdapter(launcher=SubprocessOmpPromptLauncher())
    return lambda instance, transcript_dir: adapter.agent_prompt_runner(
        instance=instance,
        transcript_dir=transcript_dir,
    )


def _omp_task_agent() -> TaskAgent:
    return OmpAdapter(task_launcher=SubprocessOmpTaskLauncher())


def _local_smoke_prompt_runner_factory() -> AgentPromptRunnerFactory:
    adapter = LocalSmokeAgentAdapter()
    return lambda instance, transcript_dir: adapter.agent_prompt_runner(
        instance=instance,
        transcript_dir=transcript_dir,
    )


def _local_smoke_task_agent() -> TaskAgent:
    return LocalSmokeAgentAdapter()


_HARNESS_ADAPTERS: dict[str, HarnessAdapter] = {
    "claude-code": RegisteredHarnessAdapter(
        name="claude-code",
        _agent_prompt_runner_factory=_claude_code_prompt_runner_factory,
        _task_agent=_claude_code_task_agent,
    ),
    "codex": RegisteredHarnessAdapter(
        name="codex",
        _agent_prompt_runner_factory=_codex_prompt_runner_factory,
        _task_agent=_codex_task_agent,
    ),
    "local-smoke": RegisteredHarnessAdapter(
        name="local-smoke",
        _agent_prompt_runner_factory=_local_smoke_prompt_runner_factory,
        _task_agent=_local_smoke_task_agent,
    ),
    "pi": RegisteredHarnessAdapter(
        name="pi",
        _agent_prompt_runner_factory=_pi_prompt_runner_factory,
        _task_agent=_pi_task_agent,
    ),
    "omp": RegisteredHarnessAdapter(
        name="omp",
        _agent_prompt_runner_factory=_omp_prompt_runner_factory,
        _task_agent=_omp_task_agent,
    ),
}
