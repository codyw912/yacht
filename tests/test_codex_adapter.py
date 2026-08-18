import json
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import Metrics, RuntimeInstance, RuntimeRecipe, Task
from yacht.harnesses.codex import (
    CodexAdapter,
    CodexPromptRequest,
    CodexTaskRequest,
    SubprocessCodexPromptLauncher,
    SubprocessCodexTaskLauncher,
)
from yacht.preflight import AgentPromptResult, CommandResult
from yacht.workflows.task_attempts import AgentTaskResult


FIXTURES = Path("tests/fixtures")


class CodexAdapterTests(unittest.TestCase):
    def test_adapter_builds_native_prompt_and_task_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _runtime_instance(root)
            prompt_requests: list[CodexPromptRequest] = []
            task_requests: list[CodexTaskRequest] = []

            def prompt_launcher(request: CodexPromptRequest) -> AgentPromptResult:
                prompt_requests.append(request)
                return AgentPromptResult(0, "OK", (), request.transcript_path)

            def task_launcher(request: CodexTaskRequest) -> AgentTaskResult:
                task_requests.append(request)
                return AgentTaskResult(
                    0,
                    "OK",
                    (),
                    request.transcript_path,
                    Metrics(tokens=1, duration_seconds=0.1, usage_source="reported"),
                )

            CodexAdapter(launcher=prompt_launcher).agent_prompt_runner(
                instance=instance, transcript_dir=root / "transcripts"
            )("check", instance.env, root)
            CodexAdapter(task_launcher=task_launcher).run_task(
                instance=instance,
                task=_task(),
                prompt="solve",
                env=instance.env,
                cwd=root,
                transcript_path=root / "transcripts" / "task.json",
            )

            self.assertEqual(
                prompt_requests[0].argv,
                ("runtime", "codex", "exec", "--json", "--ephemeral"),
            )
            self.assertEqual(task_requests[0].argv, prompt_requests[0].argv)

    def test_subprocess_launchers_preserve_native_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _runtime_instance(root)

            def runner(_: CodexPromptRequest | CodexTaskRequest) -> CommandResult:
                return CommandResult(
                    0,
                    FIXTURES.joinpath("codex-exec-tool.jsonl").read_text(),
                    "",
                )

            version_calls: list[tuple[str, ...]] = []

            def version_runner(
                argv: tuple[str, ...], _: dict[str, str], __: Path
            ) -> CommandResult:
                version_calls.append(argv)
                return CommandResult(0, "codex-cli 0.147.0\n", "")

            prompt_result = CodexAdapter(
                launcher=SubprocessCodexPromptLauncher(
                    runner=runner, version_runner=version_runner
                )
            ).agent_prompt_runner(
                instance=instance, transcript_dir=root / "transcripts"
            )("check", instance.env, root)
            task_result = CodexAdapter(
                task_launcher=SubprocessCodexTaskLauncher(
                    runner=runner, version_runner=version_runner
                )
            ).run_task(
                instance=instance,
                task=_task(),
                prompt="solve",
                env=instance.env,
                cwd=root,
                transcript_path=root / "transcripts" / "task.json",
            )

            self.assertEqual(prompt_result.tool_calls, ("command_execution",))
            self.assertEqual(task_result.response, "OK")
            self.assertEqual(task_result.metrics.tokens, 2)
            self.assertEqual(task_result.metrics.usage_source, "reported")
            self.assertEqual(
                version_calls,
                [
                    ("runtime", "codex", "--version"),
                    ("runtime", "codex", "--version"),
                ],
            )
            self.assertEqual(
                task_result.machine_evidence["harness_version"], "codex-cli 0.147.0"
            )
            transcript = json.loads(task_result.transcript_path.read_text())
            self.assertEqual(transcript["machine_evidence"]["format"], "codex-jsonl")
            self.assertEqual(
                transcript["machine_evidence"]["tool_calls"], ["command_execution"]
            )
            self.assertEqual(
                transcript["machine_evidence"]["harness_version"], "codex-cli 0.147.0"
            )


def _runtime_instance(root: Path) -> RuntimeInstance:
    return RuntimeInstance(
        runtime=RuntimeRecipe(name="codex", backend="host-nix", command=("codex",)),
        temp_home=root / "home",
        workspace_path=root,
        env={"HOME": str(root / "home")},
        command_prefix=("runtime",),
        cleanup_paths=(),
    )


def _task() -> Task:
    return Task(id="task-1", title="Task", difficulty=1)


if __name__ == "__main__":
    unittest.main()
