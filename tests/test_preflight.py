import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.preflight import (
    AgentPromptResult,
    CommandResult,
    execute_preflight,
    execute_machine_preflight,
)
from yacht.regatta import load_regatta
from yacht.runtime_backend import HostNixRuntimeBackend, SetupProcessResult
from yacht.schemas import PREFLIGHT_SCHEMA, validate_preflight_document


class MachinePreflightTests(unittest.TestCase):
    def test_execute_machine_preflight_writes_passing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)
            artifact_path = root / "logbook" / "preflight" / "pi-plus-fff.json"
            commands = []

            def command_runner(
                argv: tuple[str, ...],
                env: dict[str, str],
                cwd: Path,
            ) -> CommandResult:
                commands.append((argv, env, cwd))
                return CommandResult(exit_code=0, stdout="pi 1.0\n", stderr="")

            artifact = execute_machine_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=artifact_path,
                comparison=regatta.comparisons[0],
                command_runner=command_runner,
            )

            validate_preflight_document(artifact)
            self.assertEqual(artifact["schema"], PREFLIGHT_SCHEMA)
            self.assertEqual(artifact["status"], "passed")
            self.assertEqual(artifact["comparison"], "pi-vs-pi-fff")
            self.assertEqual(artifact["vessel"], "pi-plus-fff")
            self.assertEqual(artifact["runtime"], "pi")
            self.assertEqual(artifact["workspace_path"], str(instance.workspace_path))
            self.assertEqual(artifact["temp_home"], str(instance.temp_home))
            self.assertEqual(
                artifact["command_prefix"],
                ["nix", "develop", "path:.#pi", "--command"],
            )
            self.assertEqual(
                artifact["cleanup_paths"],
                [str(path) for path in instance.cleanup_paths],
            )
            self.assertEqual(
                artifact["runtime_setup"],
                [
                    {
                        "origin": "rigging",
                        "origin_name": "pi-fff",
                        "action": "install",
                        "target": "npm:@ff-labs/pi-fff",
                        "argv": [
                            "nix",
                            "develop",
                            "path:.#pi",
                            "--command",
                            "pi",
                            "install",
                            "npm:@ff-labs/pi-fff",
                        ],
                        "exit_code": 0,
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            )
            self.assertEqual(
                artifact["secret_refs"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "redacted": True,
                    }
                ],
            )
            self.assertEqual(
                [check["name"] for check in artifact["checks"]],
                ["pi-present", "runtime-home-isolated", "fff-mode", "fff-state-isolated"],
            )
            self.assertEqual(_check_by_name(artifact, "pi-present")["origin"], "runtime")
            self.assertEqual(
                _check_by_name(artifact, "fff-mode")["origin"],
                "rigging",
            )
            self.assertEqual(
                _check_by_name(artifact, "fff-mode")["origin_name"],
                "pi-fff",
            )
            self.assertEqual(
                commands[0][0],
                (
                    "nix",
                    "develop",
                    "path:.#pi",
                    "--command",
                    "pi",
                    "--version",
                ),
            )
            self.assertEqual(commands[0][1]["HOME"], str(instance.temp_home))
            self.assertEqual(commands[0][2], instance.workspace_path)
            saved = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(saved, artifact)

    def test_execute_machine_preflight_fails_missing_env_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)
            env = dict(instance.env)
            del env["PI_FFF_MODE"]
            instance = replace(instance, env=env)

            artifact = execute_machine_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                command_runner=_passing_command,
            )

            self.assertEqual(artifact["status"], "failed")
            fff_mode = _check_by_name(artifact, "fff-mode")
            self.assertEqual(fff_mode["status"], "failed")
            self.assertEqual(fff_mode["evidence"]["missing_env"], ["PI_FFF_MODE"])

    def test_execute_machine_preflight_fails_path_outside_trial_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)
            env = dict(instance.env)
            env["FFF_HISTORY_DB"] = str(root / "shared" / "fff-history.sqlite")
            instance = replace(instance, env=env)

            artifact = execute_machine_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                command_runner=_passing_command,
            )

            self.assertEqual(artifact["status"], "failed")
            state_check = _check_by_name(artifact, "fff-state-isolated")
            self.assertEqual(state_check["status"], "failed")
            self.assertEqual(
                state_check["evidence"]["outside_trial_home"],
                {"FFF_HISTORY_DB": str(root / "shared" / "fff-history.sqlite")},
            )

    def test_execute_machine_preflight_honors_optional_recipe(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            "[riggings.pi-fff.preflight]\nrequired = true",
            "[riggings.pi-fff.preflight]\nrequired = false",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(config, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)
            instance = HostNixRuntimeBackend(setup_runner=_passing_setup).prepare(
                regatta=regatta,
                vessel=regatta.vessels[1],
                trial_root=root / "trial",
                workspace_path=workspace_path,
                secret_values={"anthropic": "test-secret"},
            )
            env = dict(instance.env)
            del env["PI_FFF_MODE"]
            instance = replace(instance, env=env)

            artifact = execute_machine_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                command_runner=_passing_command,
            )

            self.assertEqual(artifact["status"], "passed")
            fff_mode = _check_by_name(artifact, "fff-mode")
            self.assertEqual(fff_mode["status"], "failed")
            self.assertFalse(fff_mode["required"])

    def test_execute_preflight_passes_agent_prompt_with_tool_call_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)
            calls = []

            def agent_runner(
                prompt: str,
                env: dict[str, str],
                cwd: Path,
            ) -> AgentPromptResult:
                calls.append((prompt, env, cwd))
                return AgentPromptResult(
                    exit_code=0,
                    response=(
                        "```json\n"
                        '{"available": true, "configured": true, "tool_calls": ["fffind"]}'
                        "\n```"
                    ),
                    tool_calls=("fffind",),
                    transcript_path=root / "transcripts" / "fff.json",
                )

            artifact = execute_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                comparison=regatta.comparisons[0],
                command_runner=_passing_command,
                agent_prompt_runner=agent_runner,
            )

            self.assertEqual(artifact["status"], "passed")
            agent_check = _check_by_name(artifact, "fff-headless-smoke")
            self.assertEqual(agent_check["status"], "passed")
            self.assertEqual(agent_check["origin"], "rigging")
            self.assertEqual(agent_check["origin_name"], "pi-fff")
            self.assertEqual(
                agent_check["evidence"],
                {
                    "prompt": "preflights/pi-fff.md",
                    "exit_code": 0,
                    "response": (
                        "```json\n"
                        '{"available": true, "configured": true, "tool_calls": ["fffind"]}'
                        "\n```"
                    ),
                    "expected_tool_calls": ["fffind"],
                    "response_json": {
                        "available": True,
                        "configured": True,
                        "tool_calls": ["fffind"],
                    },
                    "tool_calls": ["fffind"],
                    "transcript_path": str(root / "transcripts" / "fff.json"),
                },
            )
            self.assertEqual(calls[0][0], "preflights/pi-fff.md")
            self.assertEqual(calls[0][1]["HOME"], str(instance.temp_home))
            self.assertEqual(calls[0][2], instance.workspace_path)

    def test_execute_preflight_reads_agent_prompt_file_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)
            prompt_path = instance.workspace_path / "preflights" / "pi-fff.md"
            prompt_path.parent.mkdir(parents=True)
            prompt_path.write_text("Confirm fff with fffind.\n", encoding="utf-8")
            calls = []

            def agent_runner(
                prompt: str,
                env: dict[str, str],
                cwd: Path,
            ) -> AgentPromptResult:
                calls.append((prompt, env, cwd))
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true, "configured": true}',
                    tool_calls=("fffind",),
                    transcript_path=None,
                )

            artifact = execute_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                comparison=regatta.comparisons[0],
                command_runner=_passing_command,
                agent_prompt_runner=agent_runner,
            )

            self.assertEqual(artifact["status"], "passed")
            agent_check = _check_by_name(artifact, "fff-headless-smoke")
            self.assertEqual(calls[0][0], "Confirm fff with fffind.\n")
            self.assertEqual(agent_check["evidence"]["prompt"], calls[0][0])

    def test_execute_preflight_fails_agent_prompt_without_expected_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)

            def agent_runner(
                prompt: str,
                env: dict[str, str],
                cwd: Path,
            ) -> AgentPromptResult:
                return AgentPromptResult(
                    exit_code=0,
                    response=(
                        '{"available": true, "configured": true, "tool_calls": []}'
                    ),
                    tool_calls=(),
                    transcript_path=None,
                )

            artifact = execute_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                command_runner=_passing_command,
                agent_prompt_runner=agent_runner,
            )

            self.assertEqual(artifact["status"], "failed")
            agent_check = _check_by_name(artifact, "fff-headless-smoke")
            self.assertEqual(agent_check["status"], "failed")
            self.assertEqual(agent_check["evidence"]["missing_tool_calls"], ["fffind"])

    def test_execute_preflight_fails_agent_prompt_without_configured_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)

            def agent_runner(
                prompt: str,
                env: dict[str, str],
                cwd: Path,
            ) -> AgentPromptResult:
                return AgentPromptResult(
                    exit_code=0,
                    response='{"available": true}',
                    tool_calls=("fff",),
                    transcript_path=None,
                )

            artifact = execute_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                command_runner=_passing_command,
                agent_prompt_runner=agent_runner,
            )

            self.assertEqual(artifact["status"], "failed")
            agent_check = _check_by_name(artifact, "fff-headless-smoke")
            self.assertEqual(agent_check["status"], "failed")
            self.assertEqual(
                agent_check["evidence"]["response_contract_errors"],
                ["response.configured must be true"],
            )

    def test_execute_preflight_marks_required_agent_prompt_error_without_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta, instance = _prepared_runtime(root, vessel_index=1)

            artifact = execute_preflight(
                regatta=regatta,
                vessel=regatta.vessels[1],
                instance=instance,
                artifact_path=root / "logbook" / "preflight" / "pi-plus-fff.json",
                command_runner=_passing_command,
            )

            self.assertEqual(artifact["status"], "failed")
            agent_check = _check_by_name(artifact, "fff-headless-smoke")
            self.assertEqual(agent_check["status"], "error")
            self.assertEqual(
                agent_check["evidence"]["error"],
                "agent prompt runner not configured",
            )


def _prepared_runtime(root: Path, vessel_index: int):
    config_path = root / "regatta.toml"
    workspace_path = root / "workspace"
    config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
    workspace_path.mkdir()
    regatta = load_regatta(config_path)
    instance = HostNixRuntimeBackend(setup_runner=_passing_setup).prepare(
        regatta=regatta,
        vessel=regatta.vessels[vessel_index],
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
