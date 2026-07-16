import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yacht.harnesses.claude_code import (
    ClaudeCodeAdapter,
    ClaudeCodeAdapterNotConfigured,
    ClaudeCodePromptRequest,
    ClaudeCodeStreamJsonError,
    ClaudeCodeTaskRequest,
    SubprocessClaudeCodePromptLauncher,
    SubprocessClaudeCodeTaskLauncher,
)
from yacht.preflight import AgentPromptResult, CommandResult
from yacht.domain.model import (
    ConfigError,
    Metrics,
    RuntimeInstance,
    RuntimeRecipe,
    Task,
)
from yacht.workflows.task_attempt_runner import run_task_attempts
from yacht.workflows.task_attempts import AgentTaskResult


CLAUDE_CODE_IMAGE = "yacht/claude-code-runtime:claude-2.1.211"

CLAUDE_CODE_CONTAINER_CONFIG = f"""
[regatta]
name = "container-claude-code-smoke"

[preflight]
failure_policy = "abort-group"

[course]
name = "container-runtime-smoke"
tasks = [
  {{ id = "container-claude-code-smoke-1", title = "Container Claude Code runtime smoke", difficulty = 1 }},
]

[runtimes.claude-code-container]
backend = "container"
harness = "claude-code"
image = "{CLAUDE_CODE_IMAGE}"
command = ["claude", "--model", "claude-haiku-4-5"]
container_home = "/home/yacht"
container_workspace = "/workspace"

[runtimes.claude-code-container.preflight]
required = true
checks = [
  {{ name = "claude-present", kind = "command", command = ["claude", "--version"] }},
  {{ name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] }},
]

[[vessels]]
name = "claude-code-container-a"
model = "claude-haiku-4-5"
runtime = "claude-code-container"

[[vessels]]
name = "claude-code-container-b"
model = "claude-haiku-4-5"
runtime = "claude-code-container"

[[comparisons]]
name = "container-claude-code-runtime"
course = "container-runtime-smoke"
vessels = ["claude-code-container-a", "claude-code-container-b"]
"""


def _stream(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _init_event() -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "cwd": "/workspace",
        "session_id": "7522b322-2187-4552-b3ef-456ef79deba3",
        "tools": ["Task", "Bash", "Edit", "Read", "Write"],
        "model": "claude-haiku-4-5",
        "permissionMode": "bypassPermissions",
        "claude_code_version": "2.1.211",
    }


def _assistant_tool_use_event(name: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": "claude-haiku-4-5",
            "content": [{"type": "tool_use", "id": "toolu_01", "name": name}],
        },
        "session_id": "7522b322-2187-4552-b3ef-456ef79deba3",
    }


def _success_result_event(result_text: str) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 4523,
        "duration_api_ms": 4100,
        "num_turns": 3,
        "result": result_text,
        "session_id": "7522b322-2187-4552-b3ef-456ef79deba3",
        "total_cost_usd": 0.0123,
        "usage": {
            "input_tokens": 12,
            "cache_creation_input_tokens": 345,
            "cache_read_input_tokens": 678,
            "output_tokens": 90,
            "server_tool_use": {"web_search_requests": 0},
            "service_tier": "standard",
            "cache_creation": {"ephemeral_5m_input_tokens": 345},
        },
        "modelUsage": {},
    }


# Captured from the pinned image with an invalid API key: the CLI exits 1
# and still emits a complete result event with is_error and zeroed usage.
AUTH_FAILURE_STREAM = _stream(
    _init_event(),
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": "<synthetic>",
            "content": [
                {"type": "text", "text": "Invalid API key · Fix external API key"}
            ],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
        "error": "authentication_failed",
    },
    {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": 401,
        "duration_ms": 231,
        "duration_api_ms": 0,
        "num_turns": 1,
        "result": "Invalid API key · Fix external API key",
        "session_id": "7522b322-2187-4552-b3ef-456ef79deba3",
        "total_cost_usd": 0,
        "usage": {
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
            "service_tier": "standard",
        },
        "terminal_reason": "api_error",
    },
)


class ClaudeCodeAdapterTests(unittest.TestCase):
    def test_default_adapter_refuses_to_run_headless_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _container_instance(root)

            runner = ClaudeCodeAdapter().agent_prompt_runner(
                instance=instance,
                transcript_dir=root / "transcripts",
            )

            with self.assertRaisesRegex(
                ClaudeCodeAdapterNotConfigured,
                "Claude Code headless prompt launcher is not configured",
            ):
                runner("Confirm availability.", instance.env, instance.workspace_path)

    def test_default_adapter_refuses_to_run_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _container_instance(root)

            with self.assertRaisesRegex(
                ClaudeCodeAdapterNotConfigured,
                "Claude Code task launcher is not configured",
            ):
                ClaudeCodeAdapter().run_task(
                    instance=instance,
                    task=_task(),
                    prompt="Task ID: task-1\n",
                    env=instance.env,
                    cwd=instance.workspace_path,
                    transcript_path=root / "transcripts" / "claude-task.json",
                )

    def test_run_task_refuses_permission_bypass_outside_container(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _host_instance(root)
            requests = []

            def launcher(request: ClaudeCodeTaskRequest) -> AgentTaskResult:
                requests.append(request)
                raise AssertionError("launcher must not run")

            with self.assertRaisesRegex(
                ConfigError,
                "claude-code task attempts run with "
                "--dangerously-skip-permissions, which is only allowed inside "
                "an isolated container runtime: runtime claude-host uses "
                "backend host-nix",
            ):
                ClaudeCodeAdapter(task_launcher=launcher).run_task(
                    instance=instance,
                    task=_task(),
                    prompt="Task ID: task-1\n",
                    env=instance.env,
                    cwd=instance.workspace_path,
                    transcript_path=root / "transcripts" / "claude-task.json",
                )
            self.assertEqual(requests, [])

    def test_prompt_runner_appends_headless_flags_without_permission_bypass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _container_instance(root)
            requests = []

            def launcher(request: ClaudeCodePromptRequest) -> AgentPromptResult:
                requests.append(request)
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true, "configured": true}',
                    tool_calls=(),
                    transcript_path=request.transcript_path,
                )

            runner = ClaudeCodeAdapter(launcher=launcher).agent_prompt_runner(
                instance=instance,
                transcript_dir=root / "transcripts",
            )

            runner("Confirm availability.", instance.env, instance.workspace_path)

            self.assertEqual(len(requests), 1)
            self.assertEqual(
                requests[0].argv,
                (
                    "docker",
                    "run",
                    "--rm",
                    CLAUDE_CODE_IMAGE,
                    "claude",
                    "--model",
                    "claude-haiku-4-5",
                    "--print",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                ),
            )
            self.assertNotIn("--dangerously-skip-permissions", requests[0].argv)
            self.assertEqual(
                requests[0].transcript_path,
                root / "transcripts" / "claude-code-headless-prompt.json",
            )

    def test_run_task_appends_permission_bypass_on_container_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _container_instance(root)
            requests = []

            def launcher(request: ClaudeCodeTaskRequest) -> AgentTaskResult:
                requests.append(request)
                return AgentTaskResult(
                    exit_code=0,
                    response="Done.",
                    tool_calls=("Bash",),
                    transcript_path=request.transcript_path,
                    metrics=Metrics(tokens=42, duration_seconds=3.5),
                )

            result = ClaudeCodeAdapter(task_launcher=launcher).run_task(
                instance=instance,
                task=_task(),
                prompt="Task ID: task-1\n",
                env=instance.env,
                cwd=instance.workspace_path,
                transcript_path=root / "transcripts" / "claude-task.json",
            )

            self.assertEqual(result.tool_calls, ("Bash",))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].task_id, "task-1")
            self.assertEqual(
                requests[0].argv[-5:],
                (
                    "--print",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--dangerously-skip-permissions",
                ),
            )

    def test_subprocess_task_launcher_extracts_stream_json_machine_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stdout = _stream(
                _init_event(),
                _assistant_tool_use_event("Bash"),
                _assistant_tool_use_event("Edit"),
                _assistant_tool_use_event("Bash"),
                _success_result_event("Done. Fixed the bug."),
            )

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                return CommandResult(exit_code=0, stdout=stdout, stderr="")

            request = _task_request(root)

            with patch(
                "yacht.harnesses.claude_code.time.perf_counter",
                side_effect=(100.0, 102.3456),
            ):
                result = SubprocessClaudeCodeTaskLauncher(runner=runner)(request)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.response, "Done. Fixed the bug.")
            self.assertEqual(result.tool_calls, ("Bash", "Edit"))
            self.assertEqual(result.metrics.tokens, 12 + 345 + 678 + 90)
            self.assertEqual(result.metrics.duration_seconds, 2.346)
            self.assertEqual(
                result.machine_evidence,
                {
                    "format": "claude-code-stream-json",
                    "event_count": 5,
                    "model": "claude-haiku-4-5",
                    "session_id": "7522b322-2187-4552-b3ef-456ef79deba3",
                    "subtype": "success",
                    "is_error": False,
                    "num_turns": 3,
                    "duration_ms": 4523,
                    "duration_api_ms": 4100,
                    "usage": {
                        "input_tokens": 12,
                        "cache_creation_input_tokens": 345,
                        "cache_read_input_tokens": 678,
                        "output_tokens": 90,
                    },
                    "cost": {"total": 0.0123},
                    "result": "Done. Fixed the bug.",
                    "tool_calls": ["Bash", "Edit"],
                },
            )

            transcript = json.loads(request.transcript_path.read_text(encoding="utf-8"))
            self.assertEqual(transcript["task_id"], "task-1")
            self.assertEqual(transcript["stdout"], stdout)
            self.assertEqual(transcript["response"], result.response)
            self.assertEqual(transcript["tool_calls"], ["Bash", "Edit"])
            self.assertEqual(transcript["machine_evidence"], result.machine_evidence)

    def test_subprocess_task_launcher_fails_loudly_on_non_stream_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                return CommandResult(exit_code=0, stdout="plain text\n", stderr="")

            request = _task_request(root)

            with self.assertRaisesRegex(
                ClaudeCodeStreamJsonError,
                "claude-code task task-1 exited 0 without a valid stream-json "
                "result message",
            ):
                SubprocessClaudeCodeTaskLauncher(runner=runner)(request)
            self.assertFalse(request.transcript_path.exists())

    def test_subprocess_task_launcher_fails_loudly_on_missing_result_event(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stdout = _stream(_init_event(), _assistant_tool_use_event("Bash"))

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                return CommandResult(exit_code=0, stdout=stdout, stderr="")

            with self.assertRaises(ClaudeCodeStreamJsonError):
                SubprocessClaudeCodeTaskLauncher(runner=runner)(_task_request(root))

    def test_subprocess_task_launcher_records_auth_failure_without_estimating(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                return CommandResult(exit_code=1, stdout=AUTH_FAILURE_STREAM, stderr="")

            request = _task_request(root)
            result = SubprocessClaudeCodeTaskLauncher(runner=runner)(request)

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.response, "Invalid API key · Fix external API key")
            self.assertEqual(result.metrics.tokens, 0)
            self.assertIs(result.machine_evidence["is_error"], True)
            self.assertEqual(result.machine_evidence["cost"], {"total": 0})
            self.assertTrue(request.transcript_path.is_file())

    def test_subprocess_task_launcher_records_plain_failure_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                return CommandResult(
                    exit_code=1,
                    stdout="",
                    stderr=(
                        "Error: When using --print, --output-format=stream-json "
                        "requires --verbose\n"
                    ),
                )

            request = _task_request(root)
            result = SubprocessClaudeCodeTaskLauncher(runner=runner)(request)

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.machine_evidence, {})
            self.assertEqual(result.tool_calls, ())
            transcript = json.loads(request.transcript_path.read_text(encoding="utf-8"))
            self.assertIn("requires --verbose", transcript["stderr"])

    def test_subprocess_prompt_launcher_extracts_response_from_result_event(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            response_text = (
                '{"available": true, "configured": true, "tool_calls": ["fffind"]}'
            )
            stdout = _stream(
                _init_event(),
                _assistant_tool_use_event("fffind"),
                _success_result_event(response_text),
            )

            def runner(request: ClaudeCodePromptRequest) -> CommandResult:
                return CommandResult(exit_code=0, stdout=stdout, stderr="")

            request = ClaudeCodePromptRequest(
                prompt="Confirm fff availability.",
                argv=("claude",),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "claude-prompt.json",
            )

            result = SubprocessClaudeCodePromptLauncher(runner=runner)(request)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.response, response_text)
            self.assertEqual(result.tool_calls, ("fffind",))

            transcript = json.loads(request.transcript_path.read_text(encoding="utf-8"))
            self.assertEqual(transcript["prompt"], "Confirm fff availability.")
            self.assertEqual(transcript["response"], response_text)
            self.assertEqual(
                transcript["machine_evidence"]["format"],
                "claude-code-stream-json",
            )

    def test_subprocess_prompt_launcher_falls_back_to_raw_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def runner(request: ClaudeCodePromptRequest) -> CommandResult:
                return CommandResult(
                    exit_code=0,
                    stdout='{"available": true, "configured": true}\n',
                    stderr="",
                )

            request = ClaudeCodePromptRequest(
                prompt="Confirm availability.",
                argv=("claude",),
                env={"HOME": str(root / "home")},
                cwd=root,
                transcript_path=root / "transcripts" / "claude-prompt.json",
            )

            result = SubprocessClaudeCodePromptLauncher(runner=runner)(request)

            self.assertEqual(
                result.response,
                '{"available": true, "configured": true}\n',
            )
            self.assertEqual(result.tool_calls, ())

    def test_task_attempt_runner_uses_registered_claude_code_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(CLAUDE_CODE_CONTAINER_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            requests = []

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                requests.append(request)
                return CommandResult(
                    exit_code=0,
                    stdout=_stream(
                        _init_event(),
                        _assistant_tool_use_event("Bash"),
                        _success_result_event("Done."),
                    ),
                    stderr="",
                )

            with patch(
                "yacht.harnesses.registry.SubprocessClaudeCodeTaskLauncher",
                return_value=SubprocessClaudeCodeTaskLauncher(runner=runner),
            ):
                summary = run_task_attempts(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={},
                    agent_name="claude-code",
                )

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["agent"], "claude-code")
            self.assertEqual(summary["attempt_count"], 2)
            self.assertEqual(len(requests), 2)
            self.assertEqual(
                requests[0].argv[:5],
                ("docker", "run", "--rm", "--workdir", "/workspace"),
            )
            self.assertEqual(
                requests[0].argv[-5:],
                (
                    "--print",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--dangerously-skip-permissions",
                ),
            )
            self.assertIn(CLAUDE_CODE_IMAGE, requests[0].argv)

            attempt_path = (
                logbook_dir
                / "task-attempts"
                / "container-claude-code-runtime"
                / "claude-code-container-a"
                / "container-claude-code-smoke-1.json"
            )
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            self.assertEqual(attempt["schema"], "yacht.task-attempt.v1")
            self.assertEqual(attempt["status"], "completed")
            self.assertEqual(attempt["runtime_context"]["harness"], "claude-code")
            self.assertEqual(attempt["agent"]["tool_calls"], ["Bash"])
            self.assertEqual(attempt["metrics"]["tokens"], 12 + 345 + 678 + 90)

    def test_task_attempt_runner_writes_mcp_config_into_trial_home(self) -> None:
        config = CLAUDE_CODE_CONTAINER_CONFIG.replace(
            '[[vessels]]\nname = "claude-code-container-b"\nmodel = "claude-haiku-4-5"\nruntime = "claude-code-container"\n',
            '[riggings.fff-mcp]\ntools = ["fff"]\n\n'
            "[[riggings.fff-mcp.install]]\n"
            'method = "mcp-server"\n'
            'target = "fff"\n'
            'command = ["npx", "-y", "@ff-labs/mcp-fff"]\n\n'
            '[[vessels]]\nname = "claude-code-container-b"\nmodel = "claude-haiku-4-5"\nruntime = "claude-code-container"\nrigging = ["fff-mcp"]\n',
        )
        self.assertIn("fff-mcp", config)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(config, encoding="utf-8")
            workspace_path.mkdir()

            def runner(request: ClaudeCodeTaskRequest) -> CommandResult:
                return CommandResult(
                    exit_code=0,
                    stdout=_stream(
                        _init_event(),
                        _success_result_event("Done."),
                    ),
                    stderr="",
                )

            with patch(
                "yacht.harnesses.registry.SubprocessClaudeCodeTaskLauncher",
                return_value=SubprocessClaudeCodeTaskLauncher(runner=runner),
            ):
                summary = run_task_attempts(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    secret_values={},
                    agent_name="claude-code",
                )

            self.assertEqual(summary["status"], "completed")

            attempt_path = (
                logbook_dir
                / "task-attempts"
                / "container-claude-code-runtime"
                / "claude-code-container-b"
                / "container-claude-code-smoke-1.json"
            )
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            setup_results = attempt["runtime_context"]["setup_results"]
            self.assertEqual(
                setup_results,
                [
                    {
                        "origin": "rigging",
                        "origin_name": "fff-mcp",
                        "action": "mcp-server",
                        "target": "fff",
                        "argv": [],
                        "exit_code": 0,
                    }
                ],
            )

            mcp_config_path = (
                Path(attempt["runtime_context"]["temp_home"]) / ".claude.json"
            )
            self.assertEqual(
                json.loads(mcp_config_path.read_text(encoding="utf-8")),
                {
                    "mcpServers": {
                        "fff": {
                            "command": "npx",
                            "args": ["-y", "@ff-labs/mcp-fff"],
                        }
                    }
                },
            )


def _task() -> Task:
    return Task(id="task-1", title="Fix the bug", difficulty=1)


def _task_request(root: Path) -> ClaudeCodeTaskRequest:
    return ClaudeCodeTaskRequest(
        task_id="task-1",
        task_title="Fix the bug",
        prompt="Task ID: task-1\nTitle: Fix the bug\n",
        argv=("claude", "--print", "--output-format", "stream-json", "--verbose"),
        env={"HOME": str(root / "home")},
        cwd=root,
        transcript_path=root / "transcripts" / "claude-task.json",
    )


def _host_instance(root: Path) -> RuntimeInstance:
    runtime = RuntimeRecipe(
        name="claude-host",
        backend="host-nix",
        command=("claude",),
        harness="claude-code",
    )
    return RuntimeInstance(
        runtime=runtime,
        temp_home=root / "home",
        workspace_path=root / "workspace",
        env={"HOME": str(root / "home")},
        command_prefix=(),
        cleanup_paths=(),
    )


def _container_instance(root: Path) -> RuntimeInstance:
    runtime = RuntimeRecipe(
        name="claude-container",
        backend="container",
        command=("claude", "--model", "claude-haiku-4-5"),
        harness="claude-code",
        image=CLAUDE_CODE_IMAGE,
    )
    return RuntimeInstance(
        runtime=runtime,
        temp_home=root / "home",
        workspace_path=root / "workspace",
        env={"HOME": "/home/yacht"},
        command_prefix=("docker", "run", "--rm", CLAUDE_CODE_IMAGE),
        cleanup_paths=(),
    )


if __name__ == "__main__":
    unittest.main()
