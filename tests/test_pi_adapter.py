import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_provisioning import PI_FFF_TYPED_INSTALL, PI_WITH_FFF_CONFIG
from yacht.pi_adapter import (
    PiAdapter,
    PiAdapterNotConfigured,
    PiPromptRequest,
    PiTaskRequest,
    SubprocessPiPromptLauncher,
    SubprocessPiTaskLauncher,
    _run_pi_task_subprocess,
)
from yacht.preflight import AgentPromptResult, CommandResult, execute_preflight
from yacht.regatta import ConfigError, Metrics, load_regatta
from yacht.runtime_backend import HostNixRuntimeBackend, SetupProcessResult
from yacht.task_attempt_runner import run_task_attempts
from yacht.task_attempts import AgentTaskResult


class PiAdapterTests(unittest.TestCase):
    def test_default_adapter_refuses_to_run_headless_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, instance = _prepared_runtime(root)
            adapter = PiAdapter()

            runner = adapter.agent_prompt_runner(
                instance=instance,
                transcript_dir=root / "transcripts",
            )

            with self.assertRaisesRegex(
                PiAdapterNotConfigured,
                "Pi headless prompt launcher is not configured",
            ):
                runner("preflights/pi-fff.md", instance.env, instance.workspace_path)

    def test_default_adapter_refuses_to_run_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root)

            with self.assertRaisesRegex(
                PiAdapterNotConfigured,
                "Pi task launcher is not configured",
            ):
                PiAdapter().run_task(
                    instance=instance,
                    task=regatta.course.tasks[0],
                    prompt="Task ID: django__django-11099\nTitle: Fix Django issue\n",
                    env=instance.env,
                    cwd=instance.workspace_path,
                    transcript_path=root / "transcripts" / "pi-task.json",
                )

    def test_adapter_wraps_injected_launcher_as_agent_prompt_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, instance = _prepared_runtime(root)
            requests = []

            def launcher(request: PiPromptRequest) -> AgentPromptResult:
                requests.append(request)
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true, "configured": true}',
                    tool_calls=("fff",),
                    transcript_path=request.transcript_path,
                )

            runner = PiAdapter(launcher=launcher).agent_prompt_runner(
                instance=instance,
                transcript_dir=root / "transcripts",
            )

            result = runner("preflights/pi-fff.md", instance.env, instance.workspace_path)

            self.assertEqual(result.tool_calls, ("fff",))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].prompt, "preflights/pi-fff.md")
            self.assertEqual(
                requests[0].argv,
                (
                    "nix",
                    "develop",
                    "path:.#pi",
                    "--command",
                    "pi",
                ),
            )
            self.assertEqual(requests[0].env["HOME"], str(instance.temp_home))
            self.assertEqual(requests[0].cwd, instance.workspace_path)
            self.assertEqual(
                requests[0].transcript_path,
                root / "transcripts" / "pi-headless-prompt.json",
            )

    def test_adapter_wraps_injected_task_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root)
            requests = []

            def launcher(request: PiTaskRequest) -> AgentTaskResult:
                requests.append(request)
                return AgentTaskResult(
                    exit_code=0,
                    response='{"completed": true, "tool_calls": ["fff"]}',
                    tool_calls=("fff",),
                    transcript_path=request.transcript_path,
                    metrics=Metrics(tokens=42, duration_seconds=3.5),
                )

            result = PiAdapter(task_launcher=launcher).run_task(
                instance=instance,
                task=regatta.course.tasks[0],
                prompt="Task ID: django__django-11099\nTitle: Fix Django issue\n",
                env=instance.env,
                cwd=instance.workspace_path,
                transcript_path=root / "transcripts" / "pi-task.json",
            )

            self.assertEqual(result.tool_calls, ("fff",))
            self.assertEqual(result.metrics.tokens, 42)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].task_id, "django__django-11099")
            self.assertEqual(
                requests[0].argv,
                (
                    "nix",
                    "develop",
                    "path:.#pi",
                    "--command",
                    "pi",
                ),
            )
            self.assertEqual(requests[0].env["HOME"], str(instance.temp_home))
            self.assertEqual(requests[0].cwd, instance.workspace_path)

    def test_task_attempt_runner_can_use_injected_pi_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(_config_without_install(), encoding="utf-8")
            workspace_path.mkdir()
            requests = []

            def launcher(request: PiTaskRequest) -> AgentTaskResult:
                requests.append(request)
                return AgentTaskResult(
                    exit_code=0,
                    response='{"completed": true, "tool_calls": ["fff"]}',
                    tool_calls=("fff",),
                    transcript_path=request.transcript_path,
                    metrics=Metrics(tokens=42, duration_seconds=3.5),
                )

            with patch(
                "yacht.benchmark_adapters.SweBenchAdapter.task_with_context",
                autospec=True,
                side_effect=lambda self, *, task, adapter: task,
            ), patch(
                "yacht.benchmark_adapters.SweBenchAdapter.workspace_for_attempt",
                autospec=True,
                return_value=workspace_path,
            ):
                summary = run_task_attempts(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                    agent_name="pi",
                    task_agent=PiAdapter(task_launcher=launcher),
                )

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["agent"], "pi")
            self.assertEqual(summary["attempt_count"], 2)
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[0].task_id, "django__django-11099")
            self.assertEqual(requests[0].argv[-1], "pi")

            attempt_path = (
                logbook_dir
                / "task-attempts"
                / "pi-vs-pi-fff"
                / "pi-plus-fff"
                / "django__django-11099.json"
            )
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            self.assertEqual(attempt["schema"], "yacht.task-attempt.v1")
            self.assertEqual(attempt["agent"]["tool_calls"], ["fff"])
            self.assertEqual(attempt["metrics"]["tokens"], 42)
            self.assertNotIn("test-secret", json.dumps(attempt))

    def test_task_attempt_runner_prepares_container_runtime_for_pi_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            workspace_path.mkdir()
            requests = []

            def launcher(request: PiTaskRequest) -> AgentTaskResult:
                requests.append(request)
                return AgentTaskResult(
                    exit_code=0,
                    response='{"completed": true, "tool_calls": []}',
                    tool_calls=(),
                    transcript_path=request.transcript_path,
                    metrics=Metrics(tokens=18, duration_seconds=1.0),
                )

            summary = run_task_attempts(
                config_path=Path("examples/container-pi-runtime-smoke.toml"),
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                secret_values={},
                agent_name="pi",
                task_agent=PiAdapter(task_launcher=launcher),
            )

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["attempt_count"], 2)
            self.assertEqual(len(requests), 2)
            self.assertEqual(
                requests[0].argv[:5],
                ("docker", "run", "--rm", "--workdir", "/workspace"),
            )
            self.assertEqual(
                requests[0].argv[-2:],
                ("yacht/pi-agent-runtime:pi-0.74.0", "pi"),
            )
            self.assertEqual(requests[0].env["HOME"], "/home/yacht")

            attempt_path = (
                logbook_dir
                / "task-attempts"
                / "container-pi-runtime"
                / "pi-container-a"
                / "container-pi-smoke-1.json"
            )
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            self.assertEqual(attempt["runtime_context"]["backend"], "container")
            self.assertEqual(
                attempt["runtime_context"]["command_prefix"][:5],
                ["docker", "run", "--rm", "--workdir", "/workspace"],
            )

    def test_task_attempt_runner_requires_injected_pi_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            with self.assertRaisesRegex(
                ConfigError,
                "Pi task attempt agent requires an injected task agent",
            ):
                run_task_attempts(
                    config_path=config_path,
                    logbook_dir=root / "logbook",
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                    agent_name="pi",
                )

    def test_adapter_runner_can_satisfy_agent_prompt_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root)

            def launcher(request: PiPromptRequest) -> AgentPromptResult:
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true, "configured": true}',
                    tool_calls=("fffind",),
                    transcript_path=request.transcript_path,
                )

            artifact = execute_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                comparison=regatta.comparisons[0],
                command_runner=_passing_command,
                agent_prompt_runner=PiAdapter(launcher=launcher).agent_prompt_runner(
                    instance=instance,
                    transcript_dir=root / "transcripts",
                ),
            )

            self.assertEqual(artifact["status"], "passed")
            agent_check = _check_by_name(artifact, "fff-headless-smoke")
            self.assertEqual(agent_check["status"], "passed")
            self.assertEqual(
                agent_check["evidence"]["transcript_path"],
                str(root / "transcripts" / "pi-headless-prompt.json"),
            )

    def test_subprocess_launcher_captures_prompt_result_and_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests = []

            def runner(request: PiPromptRequest) -> CommandResult:
                requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout=(
                        "```json\n"
                        '{"available": true, "configured": true, '
                        '"tool_calls": ["fff"]}\n'
                        "```\n"
                    ),
                    stderr="",
                )

            request = PiPromptRequest(
                prompt="Confirm fff availability.",
                argv=("pi",),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "pi.json",
            )

            result = SubprocessPiPromptLauncher(runner=runner)(request)

            self.assertEqual(requests, [request])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                result.response,
                (
                    "```json\n"
                    '{"available": true, "configured": true, "tool_calls": ["fff"]}\n'
                    "```\n"
                ),
            )
            self.assertEqual(result.tool_calls, ("fff",))
            self.assertEqual(result.transcript_path, request.transcript_path)

            transcript = json.loads(
                request.transcript_path.read_text(encoding="utf-8")
            )
            self.assertEqual(transcript["prompt"], "Confirm fff availability.")
            self.assertEqual(transcript["argv"], ["pi"])
            self.assertEqual(transcript["cwd"], str(root))
            self.assertEqual(transcript["exit_code"], 0)
            self.assertEqual(transcript["stdout"], result.response)
            self.assertEqual(transcript["tool_calls"], ["fff"])

    def test_subprocess_prompt_launcher_extracts_pi_jsonl_machine_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pi_stdout = "\n".join(
                [
                    json.dumps({"type": "session", "version": 3}),
                    json.dumps(
                        {
                            "type": "message_end",
                            "message": {
                                "role": "assistant",
                                "api": "anthropic-messages",
                                "provider": "anthropic",
                                "model": "claude-haiku-4-5",
                                "responseId": "msg_123",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": (
                                            "```json\n"
                                            '{"available": true, "configured": true, '
                                            '"tool_calls": ["fffind"]}\n'
                                            "```"
                                        ),
                                    }
                                ],
                                "usage": {
                                    "input": 5,
                                    "output": 7,
                                    "cacheRead": 0,
                                    "cacheWrite": 0,
                                    "totalTokens": 12,
                                    "cost": {
                                        "input": 0.000005,
                                        "output": 0.000035,
                                        "cacheRead": 0,
                                        "cacheWrite": 0,
                                        "total": 0.00004,
                                    },
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn_end",
                            "toolResults": [{"toolName": "fffind"}],
                        }
                    ),
                ]
            )

            def runner(request: PiPromptRequest) -> CommandResult:
                return CommandResult(exit_code=0, stdout=pi_stdout, stderr="")

            request = PiPromptRequest(
                prompt="Confirm fff availability.",
                argv=("pi", "--print", "--mode", "json"),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "pi.json",
            )

            result = SubprocessPiPromptLauncher(runner=runner)(request)

            self.assertEqual(
                result.response,
                (
                    "```json\n"
                    '{"available": true, "configured": true, '
                    '"tool_calls": ["fffind"]}\n'
                    "```"
                ),
            )
            self.assertEqual(result.tool_calls, ("fffind",))

            transcript = json.loads(
                request.transcript_path.read_text(encoding="utf-8")
            )
            self.assertEqual(transcript["stdout"], pi_stdout)
            self.assertEqual(transcript["response"], result.response)
            self.assertEqual(transcript["tool_calls"], ["fffind"])
            self.assertEqual(transcript["machine_evidence"]["tool_calls"], ["fffind"])

    def test_subprocess_task_launcher_captures_result_and_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests = []

            def runner(request: PiTaskRequest) -> CommandResult:
                requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout='{"completed": true, "tool_calls": ["fff"]}\n',
                    stderr="",
                )

            request = PiTaskRequest(
                task_id="django__django-11099",
                task_title="Fix Django issue",
                prompt="Task ID: django__django-11099\nTitle: Fix Django issue\n",
                argv=("pi",),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "pi-task.json",
            )

            with patch(
                "yacht.pi_adapter.time.perf_counter",
                side_effect=(100.0, 102.3456),
            ):
                result = SubprocessPiTaskLauncher(runner=runner)(request)

            self.assertEqual(requests, [request])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                result.response,
                '{"completed": true, "tool_calls": ["fff"]}\n',
            )
            self.assertEqual(result.tool_calls, ("fff",))
            self.assertEqual(result.transcript_path, request.transcript_path)
            self.assertGreater(result.metrics.tokens, 0)
            self.assertEqual(result.metrics.duration_seconds, 2.346)
            self.assertEqual(result.machine_evidence, {})

            transcript = json.loads(
                request.transcript_path.read_text(encoding="utf-8")
            )
            self.assertEqual(transcript["task_id"], "django__django-11099")
            self.assertEqual(transcript["task_title"], "Fix Django issue")
            self.assertEqual(transcript["prompt"], request.prompt)
            self.assertEqual(transcript["argv"], ["pi"])
            self.assertEqual(transcript["cwd"], str(root))
            self.assertEqual(transcript["exit_code"], 0)
            self.assertEqual(transcript["stdout"], result.response)
            self.assertEqual(transcript["stderr"], "")
            self.assertEqual(transcript["tool_calls"], ["fff"])
            self.assertEqual(transcript["duration_seconds"], 2.346)
            self.assertNotIn("machine_evidence", transcript)

    def test_subprocess_task_launcher_extracts_pi_jsonl_machine_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pi_stdout = "\n".join(
                [
                    json.dumps({"type": "session", "version": 3}),
                    json.dumps(
                        {
                            "type": "message_end",
                            "message": {
                                "role": "assistant",
                                "api": "anthropic-messages",
                                "provider": "anthropic",
                                "model": "claude-haiku-4-5",
                                "responseId": "msg_123",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": '{"completed": true, "tool_calls": []}',
                                    }
                                ],
                                "usage": {
                                    "input": 5,
                                    "output": 7,
                                    "cacheRead": 0,
                                    "cacheWrite": 0,
                                    "totalTokens": 12,
                                    "cost": {
                                        "input": 0.000005,
                                        "output": 0.000035,
                                        "cacheRead": 0,
                                        "cacheWrite": 0,
                                        "total": 0.00004,
                                    },
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn_end",
                            "toolResults": [{"toolName": "fff"}],
                        }
                    ),
                ]
            )

            def runner(request: PiTaskRequest) -> CommandResult:
                return CommandResult(exit_code=0, stdout=pi_stdout, stderr="")

            request = PiTaskRequest(
                task_id="container-pi-smoke-1",
                task_title="Container Pi runtime smoke",
                prompt="Task ID: container-pi-smoke-1\n",
                argv=("pi", "--print", "--mode", "json"),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "pi-task.json",
            )

            result = SubprocessPiTaskLauncher(runner=runner)(request)

            self.assertEqual(
                result.response,
                '{"completed": true, "tool_calls": []}',
            )
            self.assertEqual(result.tool_calls, ("fff",))
            self.assertEqual(result.metrics.tokens, 12)
            self.assertEqual(
                result.machine_evidence,
                {
                    "format": "pi-jsonl",
                    "event_count": 3,
                    "api": "anthropic-messages",
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5",
                    "response_id": "msg_123",
                    "usage": {
                        "input": 5,
                        "output": 7,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 12,
                    },
                    "cost": {
                        "input": 0.000005,
                        "output": 0.000035,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "total": 0.00004,
                    },
                    "tool_calls": ["fff"],
                },
            )

            transcript = json.loads(
                request.transcript_path.read_text(encoding="utf-8")
            )
            self.assertEqual(transcript["response"], result.response)
            self.assertEqual(transcript["machine_evidence"], result.machine_evidence)

    def test_pi_task_subprocess_preserves_host_path_for_docker_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calls = []

            def run(
                argv,
                *,
                cwd,
                env,
                input,
                capture_output,
                check,
                text,
            ):
                calls.append(env)
                return subprocess.CompletedProcess(
                    args=argv,
                    returncode=0,
                    stdout='{"completed": true, "tool_calls": []}\n',
                    stderr="",
                )

            request = PiTaskRequest(
                task_id="container-pi-smoke-1",
                task_title="Container Pi runtime smoke",
                prompt="Task ID: container-pi-smoke-1\n",
                argv=("docker", "run", "image", "pi"),
                env={
                    "PATH": "/home/yacht/.local/state/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
                    "HOME": "/home/yacht",
                },
                cwd=root,
                transcript_path=root / "transcripts" / "pi-task.json",
            )

            with patch("yacht.pi_adapter.subprocess.run", side_effect=run):
                result = _run_pi_task_subprocess(request)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(calls[0]["PATH"], os.environ["PATH"])
            self.assertEqual(calls[0]["HOME"], "/home/yacht")

    def test_pi_task_subprocess_sends_prompt_as_message_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calls = []

            def run(
                argv,
                *,
                cwd,
                env,
                input,
                capture_output,
                check,
                text,
            ):
                calls.append((argv, input))
                return subprocess.CompletedProcess(
                    args=argv,
                    returncode=0,
                    stdout='{"completed": true, "tool_calls": []}\n',
                    stderr="",
                )

            request = PiTaskRequest(
                task_id="container-pi-smoke-1",
                task_title="Container Pi runtime smoke",
                prompt="Task ID: container-pi-smoke-1\n",
                argv=("pi", "--print"),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "pi-task.json",
            )

            with patch("yacht.pi_adapter.subprocess.run", side_effect=run):
                result = _run_pi_task_subprocess(request)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(calls[0][0], ("pi", "--print", request.prompt))
            self.assertIsNone(calls[0][1])

    def test_adapter_can_use_subprocess_task_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root)
            requests = []

            def runner(request: PiTaskRequest) -> CommandResult:
                requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout='{"completed": true, "tool_calls": ["fff"]}\n',
                    stderr="",
                )

            result = PiAdapter(
                task_launcher=SubprocessPiTaskLauncher(runner=runner)
            ).run_task(
                instance=instance,
                task=regatta.course.tasks[0],
                prompt="Task ID: django__django-11099\nTitle: Fix Django issue\n",
                env=instance.env,
                cwd=instance.workspace_path,
                transcript_path=root / "transcripts" / "pi-task.json",
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.tool_calls, ("fff",))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].argv[-1], "pi")
            self.assertTrue(result.transcript_path.is_file())


def _prepared_runtime(root: Path):
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
    workspace_path.mkdir()
    regatta = load_regatta(config_path)
    instance = HostNixRuntimeBackend(setup_runner=_passing_setup).prepare(
        regatta=regatta,
        vessel=regatta.vessels[1],
        trial_root=root / "trial",
        workspace_path=workspace_path,
        secret_values={"anthropic": "test-secret"},
    )
    return regatta, instance


def _config_without_install() -> str:
    return PI_WITH_FFF_CONFIG.replace(
        PI_FFF_TYPED_INSTALL,
        "install = []\n",
    )


def _passing_command(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> CommandResult:
    return CommandResult(exit_code=0, stdout="ok\n", stderr="")


def _passing_setup(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> SetupProcessResult:
    return SetupProcessResult(
        exit_code=0,
        stdout="",
        stderr="",
    )


def _check_by_name(artifact: dict[str, object], name: str) -> dict[str, object]:
    checks = artifact["checks"]
    assert isinstance(checks, list)
    for check in checks:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
