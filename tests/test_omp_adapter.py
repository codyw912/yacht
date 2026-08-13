import json
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import Metrics, RuntimeInstance, RuntimeRecipe, Task
from yacht.harnesses.omp import (
    OmpAdapter,
    OmpPromptRequest,
    OmpTaskRequest,
    SubprocessOmpPromptLauncher,
    SubprocessOmpTaskLauncher,
)
from yacht.preflight import AgentPromptResult, CommandResult
from yacht.workflows.task_attempts import AgentTaskResult


FIXTURES = Path("tests/fixtures")


class OmpAdapterTests(unittest.TestCase):
    def test_adapter_builds_native_prompt_and_task_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _runtime_instance(root)
            prompt_requests: list[OmpPromptRequest] = []
            task_requests: list[OmpTaskRequest] = []

            def prompt_launcher(request: OmpPromptRequest) -> AgentPromptResult:
                prompt_requests.append(request)
                return AgentPromptResult(0, "OK", (), request.transcript_path)

            def task_launcher(request: OmpTaskRequest) -> AgentTaskResult:
                task_requests.append(request)
                return AgentTaskResult(
                    0,
                    "OK",
                    (),
                    request.transcript_path,
                    Metrics(tokens=1, duration_seconds=0.1, usage_source="reported"),
                )

            OmpAdapter(launcher=prompt_launcher).agent_prompt_runner(
                instance=instance, transcript_dir=root / "transcripts"
            )("check", instance.env, root)
            OmpAdapter(task_launcher=task_launcher).run_task(
                instance=instance,
                task=_task(),
                prompt="solve",
                env=instance.env,
                cwd=root,
                transcript_path=root / "transcripts" / "task.json",
            )

            self.assertEqual(
                prompt_requests[0].argv,
                ("runtime", "omp", "-p", "--mode", "json", "--no-session"),
            )
            self.assertEqual(task_requests[0].argv, prompt_requests[0].argv)

    def test_subprocess_launchers_preserve_native_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _runtime_instance(root)

            def runner(_: OmpPromptRequest | OmpTaskRequest) -> CommandResult:
                return CommandResult(
                    0,
                    FIXTURES.joinpath("omp-tool-read.jsonl").read_text(),
                    "",
                )

            version_calls: list[tuple[str, ...]] = []

            def version_runner(
                argv: tuple[str, ...], _: dict[str, str], __: Path
            ) -> CommandResult:
                version_calls.append(argv)
                return CommandResult(0, "omp 7.2.15\n", "")

            prompt_result = OmpAdapter(
                launcher=SubprocessOmpPromptLauncher(
                    runner=runner, version_runner=version_runner
                )
            ).agent_prompt_runner(
                instance=instance, transcript_dir=root / "transcripts"
            )("check", instance.env, root)
            task_result = OmpAdapter(
                task_launcher=SubprocessOmpTaskLauncher(
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

            self.assertEqual(prompt_result.tool_calls, ("read",))
            self.assertEqual(task_result.response, "OK")
            self.assertEqual(task_result.metrics.tokens, 6204)
            self.assertEqual(task_result.metrics.usage_source, "reported")
            self.assertEqual(
                version_calls,
                [("runtime", "omp", "--version"), ("runtime", "omp", "--version")],
            )
            self.assertEqual(
                task_result.machine_evidence["harness_version"], "omp 7.2.15"
            )
            transcript = json.loads(task_result.transcript_path.read_text())
            self.assertEqual(transcript["machine_evidence"]["format"], "omp-jsonl")
            self.assertEqual(
                transcript["machine_evidence"]["harness_version"], "omp 7.2.15"
            )


def _runtime_instance(root: Path) -> RuntimeInstance:
    return RuntimeInstance(
        runtime=RuntimeRecipe(name="omp", backend="host-nix", command=("omp",)),
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
