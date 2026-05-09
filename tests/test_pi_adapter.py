import json
import tempfile
import unittest
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.pi_adapter import (
    PiAdapter,
    PiAdapterNotConfigured,
    PiPromptRequest,
    SubprocessPiPromptLauncher,
)
from yacht.preflight import AgentPromptResult, CommandResult, execute_preflight
from yacht.regatta import load_regatta
from yacht.runtime_backend import HostNixRuntimeBackend


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

    def test_adapter_wraps_injected_launcher_as_agent_prompt_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, instance = _prepared_runtime(root)
            requests = []

            def launcher(request: PiPromptRequest) -> AgentPromptResult:
                requests.append(request)
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true}',
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
                    "github:example/yacht-runtimes#pi",
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

    def test_adapter_runner_can_satisfy_agent_prompt_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root)

            def launcher(request: PiPromptRequest) -> AgentPromptResult:
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true}',
                    tool_calls=("fff",),
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
                    stdout='{"available": true, "tool_calls": ["fff"]}\n',
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
            self.assertEqual(result.response, '{"available": true, "tool_calls": ["fff"]}\n')
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


def _prepared_runtime(root: Path):
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
    workspace_path.mkdir()
    regatta = load_regatta(config_path)
    instance = HostNixRuntimeBackend().prepare(
        regatta=regatta,
        vessel=regatta.vessels[1],
        trial_root=root / "trial",
        workspace_path=workspace_path,
        secret_values={"anthropic": "test-secret"},
    )
    return regatta, instance


def _passing_command(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> CommandResult:
    return CommandResult(exit_code=0, stdout="ok\n", stderr="")


def _check_by_name(artifact: dict[str, object], name: str) -> dict[str, object]:
    checks = artifact["checks"]
    assert isinstance(checks, list)
    for check in checks:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
