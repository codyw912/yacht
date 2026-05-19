import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from yacht.preflight import AgentPromptResult, CommandResult
from yacht.preflight_runner import parse_secret_values, run_preflight
from yacht.regatta import ConfigError
from yacht.cli import main
from yacht.schemas import PREFLIGHT_SUMMARY_SCHEMA


PASSING_PREFLIGHT_CONFIG = """
[regatta]
name = "cli-preflight"

[preflight]
failure_policy = "abort-group"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[secrets.token]
source = "env"
name = "YACHT_TEST_TOKEN"

[runtimes.mock]
backend = "host-nix"
flake = "github:example/yacht-runtimes#mock"
command = ["mock-agent"]
required_secrets = ["token"]

[runtimes.mock.preflight]
required = true
checks = [
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[[vessels]]
name = "baseline"
model = "mock"
runtime = "mock"

[[vessels]]
name = "rigged"
model = "mock"
runtime = "mock"

[[comparisons]]
name = "baseline-vs-rigged"
course = "tiny-course"
vessels = ["baseline", "rigged"]
"""


FAILING_PREFLIGHT_CONFIG = PASSING_PREFLIGHT_CONFIG + """
[riggings.bad-path.env]
BAD_CACHE = "/tmp/yacht-shared-cache"

[riggings.bad-path.preflight]
required = true
checks = [
  { name = "bad-cache-isolated", kind = "path-isolation", env = ["BAD_CACHE"] },
]
"""


AGENT_PREFLIGHT_CONFIG = PASSING_PREFLIGHT_CONFIG + """
[riggings.agent-check.preflight]
required = true
checks = [
  { name = "agent-tool-smoke", kind = "agent-prompt", prompt = "confirm tool", expect_tool_calls = ["fff"] },
]
"""


UNSUPPORTED_INSTALL_CONFIG = PASSING_PREFLIGHT_CONFIG + """
[[riggings.unsupported.install]]
method = "package"
target = "pytest"
runtime = "python"
package = "pytest"
"""


CONTAINER_PREFLIGHT_CONFIG = """
[regatta]
name = "container-preflight"

[preflight]
failure_policy = "abort-group"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[secrets.token]
source = "env"
name = "YACHT_TEST_TOKEN"

[runtimes.container-pi]
backend = "container"
image = "yacht/pi-agent-runtime:pi-0.74.0"
command = ["pi"]
container_home = "/home/yacht"
container_workspace = "/workspace"
required_secrets = ["token"]

[runtimes.container-pi.preflight]
required = true
checks = [
  { name = "pi-present", kind = "command", command = ["pi", "--version"] },
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[[vessels]]
name = "baseline"
model = "mock"
runtime = "container-pi"

[[vessels]]
name = "rigged"
model = "mock"
runtime = "container-pi"

[[comparisons]]
name = "baseline-vs-rigged"
course = "tiny-course"
vessels = ["baseline", "rigged"]
"""


class CliPreflightTests(unittest.TestCase):
    def test_parse_secret_values_can_read_explicit_env_reference(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-secret"}):
            secrets = parse_secret_values(["anthropic=@env:ANTHROPIC_API_KEY"])

        self.assertEqual(secrets, {"anthropic": "env-secret"})

    def test_parse_secret_values_reports_missing_explicit_env_reference(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                ConfigError,
                "environment variable MISSING_KEY is not set for secret anthropic",
            ):
                parse_secret_values(["anthropic=@env:MISSING_KEY"])

    def test_parse_secret_values_rejects_empty_explicit_env_reference(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            with self.assertRaisesRegex(
                ConfigError,
                "environment variable ANTHROPIC_API_KEY is empty for secret anthropic",
            ):
                parse_secret_values(["anthropic=@env:ANTHROPIC_API_KEY"])

    def test_parse_secret_values_rejects_empty_literal_secret(self) -> None:
        with self.assertRaisesRegex(ConfigError, "secret anthropic must be non-empty"):
            parse_secret_values(["anthropic="])

    def test_preflight_prepares_container_runtime_and_runs_machine_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            commands = []

            def command_runner(argv, env, cwd):
                commands.append((argv, env, cwd))
                return CommandResult(exit_code=0, stdout="0.74.0\n", stderr="")

            with patch("yacht.preflight._run_command", side_effect=command_runner):
                result, logbook_dir = _run_preflight(
                    CONTAINER_PREFLIGHT_CONFIG,
                    root,
                )

            self.assertEqual(result.exit_code, 0)
            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "baseline.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "passed")
            self.assertEqual(
                artifact["command_prefix"][:5],
                ["docker", "run", "--rm", "--workdir", "/workspace"],
            )
            self.assertIn(
                "type=bind,source="
                + str(
                    logbook_dir
                    / "runtime"
                    / "baseline-vs-rigged"
                    / "baseline"
                    / "home"
                )
                + ",target=/home/yacht",
                artifact["command_prefix"],
            )
            self.assertEqual(
                artifact["temp_home"],
                str(
                    logbook_dir
                    / "runtime"
                    / "baseline-vs-rigged"
                    / "baseline"
                    / "home"
                ),
            )
            self.assertEqual(
                commands[0][0][-3:],
                ("yacht/pi-agent-runtime:pi-0.74.0", "pi", "--version"),
            )
            self.assertEqual(commands[0][1]["HOME"], "/home/yacht")
            self.assertEqual(commands[0][1]["YACHT_TEST_TOKEN"], "test-secret")
            self.assertTrue(
                (
                    logbook_dir
                    / "runtime"
                    / "baseline-vs-rigged"
                    / "baseline"
                    / "home"
                ).is_dir()
            )

    def test_preflight_writes_artifacts_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, logbook_dir = _run_preflight(PASSING_PREFLIGHT_CONFIG, Path(temp_dir))

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stderr, "")
            self.assertFalse((logbook_dir / "scorecard.json").exists())
            summary = json.loads(result.stdout)
            self.assertEqual(summary["schema"], PREFLIGHT_SUMMARY_SCHEMA)
            self.assertEqual(summary["status"], "passed")
            comparison = summary["comparisons"][0]
            self.assertEqual(comparison["name"], "baseline-vs-rigged")
            self.assertEqual(comparison["status"], "passed")
            self.assertEqual(
                [
                    (vessel["name"], vessel["status"])
                    for vessel in comparison["vessels"]
                ],
                [("baseline", "passed"), ("rigged", "passed")],
            )
            self.assertEqual(
                comparison["vessels"][0]["checks"],
                [
                    {
                        "name": "runtime-home-isolated",
                        "kind": "path-isolation",
                        "origin": "runtime",
                        "origin_name": "mock",
                        "required": True,
                        "included": True,
                        "status": "passed",
                    },
                ],
            )
            self.assertEqual(
                comparison["vessels"][0]["evidence_artifact_path"],
                str(
                    logbook_dir
                    / "preflight"
                    / "baseline-vs-rigged"
                    / "baseline.json"
                ),
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "baseline.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "passed")
            self.assertEqual(artifact["comparison"], "baseline-vs-rigged")
            self.assertEqual(artifact["secret_refs"][0]["redacted"], True)

    def test_preflight_applies_abort_group_status_without_running_tasks(self) -> None:
        config = FAILING_PREFLIGHT_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"\nrigging = ["bad-path"]',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result, logbook_dir = _run_preflight(config, Path(temp_dir))

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.stderr, "")
            self.assertFalse((logbook_dir / "scorecard.json").exists())
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "invalid")
            self.assertEqual(summary["comparisons"][0]["status"], "invalid")
            self.assertEqual(
                [
                    (vessel["name"], vessel["status"])
                    for vessel in summary["comparisons"][0]["vessels"]
                ],
                [("baseline", "passed"), ("rigged", "failed")],
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "rigged.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "failed")

    def test_preflight_blocks_unsupported_rigging_capability_before_prepare(
        self,
    ) -> None:
        config = UNSUPPORTED_INSTALL_CONFIG.replace(
            'name = "baseline"\nmodel = "mock"\nruntime = "mock"',
            (
                'name = "baseline"\nmodel = "mock"\nruntime = "mock"\n'
                'rigging = ["unsupported"]'
            ),
        ).replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            (
                'name = "rigged"\nmodel = "mock"\nruntime = "mock"\n'
                'rigging = ["unsupported"]'
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, logbook_dir, workspace_dir = _write_preflight_inputs(
                config,
                root,
            )

            summary = run_preflight(
                config_path,
                logbook_dir,
                workspace_dir,
                {"token": "test-secret"},
            )

            self.assertEqual(summary["status"], "invalid")
            baseline = summary["comparisons"][0]["vessels"][0]
            self.assertEqual(baseline["status"], "failed")
            capability_check = _check_by_name(
                baseline,
                "rigging-capability-unsupported-package",
            )
            self.assertEqual(capability_check["kind"], "runtime-capability")
            self.assertEqual(capability_check["status"], "failed")
            self.assertIn("does not support", capability_check["failure_reason"])
            artifact = json.loads(
                (
                    logbook_dir
                    / "preflight"
                    / "baseline-vs-rigged"
                    / "baseline.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(artifact["status"], "failed")
            self.assertEqual(
                artifact["checks"][0]["evidence"]["reason"],
                (
                    "runtime backend host-nix does not support rigging install "
                    "method package yet"
                ),
            )
            self.assertFalse((logbook_dir / "runtime").exists())

    def test_run_preflight_can_include_agent_prompt_checks_when_factory_is_supplied(
        self,
    ) -> None:
        config = AGENT_PREFLIGHT_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"\nrigging = ["agent-check"]',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, logbook_dir, workspace_dir = _write_preflight_inputs(
                config,
                root,
            )
            calls = []

            def runner_factory(instance, transcript_dir):
                def runner(prompt, env, cwd):
                    calls.append((prompt, env, cwd, transcript_dir))
                    return AgentPromptResult(
                        exit_code=0,
                        response='{"available": true, "configured": true}',
                        tool_calls=("fff",),
                        transcript_path=transcript_dir / "pi-headless-prompt.json",
                    )

                return runner

            summary = run_preflight(
                config_path,
                logbook_dir,
                workspace_dir,
                {"token": "test-secret"},
                agent_prompt_runner_factory=runner_factory,
            )

            self.assertEqual(summary["schema"], PREFLIGHT_SUMMARY_SCHEMA)
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(len(calls), 1)
            rigged = summary["comparisons"][0]["vessels"][1]
            self.assertEqual(
                rigged["evidence_artifact_path"],
                str(
                    logbook_dir
                    / "preflight"
                    / "baseline-vs-rigged"
                    / "rigged.json"
                ),
            )
            agent_check = _check_by_name(rigged, "agent-tool-smoke")
            self.assertTrue(agent_check["included"])
            self.assertEqual(agent_check["origin"], "rigging")
            self.assertEqual(agent_check["origin_name"], "agent-check")
            self.assertEqual(agent_check["status"], "passed")
            self.assertEqual(calls[0][0], "confirm tool")
            self.assertEqual(
                calls[0][3],
                logbook_dir
                / "transcripts"
                / "baseline-vs-rigged"
                / "rigged",
            )
            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "rigged.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            agent_check = _check_by_name(artifact, "agent-tool-smoke")
            self.assertEqual(agent_check["status"], "passed")
            self.assertEqual(agent_check["evidence"]["tool_calls"], ["fff"])

    def test_run_preflight_summary_reports_omitted_agent_prompt_checks_by_default(
        self,
    ) -> None:
        config = AGENT_PREFLIGHT_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"\nrigging = ["agent-check"]',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, logbook_dir, workspace_dir = _write_preflight_inputs(
                config,
                root,
            )

            summary = run_preflight(
                config_path,
                logbook_dir,
                workspace_dir,
                {"token": "test-secret"},
            )

            rigged = summary["comparisons"][0]["vessels"][1]
            agent_check = _check_by_name(rigged, "agent-tool-smoke")
            self.assertEqual(agent_check["status"], "omitted")
            self.assertFalse(agent_check["included"])
            self.assertEqual(
                agent_check["omitted_reason"],
                "agent preflight disabled",
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "rigged.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [check["name"] for check in artifact["checks"]],
                ["runtime-home-isolated"],
            )

    def test_preflight_cli_can_opt_into_pi_agent_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            config_path.write_text(PASSING_PREFLIGHT_CONFIG, encoding="utf-8")
            workspace_dir.mkdir()

            with patch("yacht.cli.run_preflight") as run_preflight_mock:
                run_preflight_mock.return_value = {
                    "regatta": "cli-preflight",
                    "course": "tiny-course",
                    "status": "passed",
                    "comparisons": [],
                }

                stdout = StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "preflight",
                            str(config_path),
                            "--logbook",
                            str(logbook_dir),
                            "--workspace",
                            str(workspace_dir),
                            "--secret",
                            "token=test-secret",
                            "--agent-preflight",
                            "pi",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertIsNotNone(
                run_preflight_mock.call_args.kwargs["agent_prompt_runner_factory"]
            )

    def test_preflight_dry_run_omits_agent_prompt_checks_by_default(self) -> None:
        config = AGENT_PREFLIGHT_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"\nrigging = ["agent-check"]',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, logbook_dir, workspace_dir = _write_preflight_inputs(
                config,
                root,
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "preflight",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertFalse(logbook_dir.exists())
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(payload["agent_preflight"], "none")
            rigged = payload["comparisons"][0]["vessels"][1]
            agent_check = _check_by_name(rigged, "agent-tool-smoke")
            self.assertFalse(agent_check["included"])
            self.assertEqual(
                agent_check["omitted_reason"],
                "agent preflight disabled",
            )
            self.assertEqual(agent_check["artifact_path"], None)

    def test_preflight_dry_run_includes_unsupported_rigging_capability_check(
        self,
    ) -> None:
        config = UNSUPPORTED_INSTALL_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            (
                'name = "rigged"\nmodel = "mock"\nruntime = "mock"\n'
                'rigging = ["unsupported"]'
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, logbook_dir, workspace_dir = _write_preflight_inputs(
                config,
                root,
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "preflight",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            rigged = payload["comparisons"][0]["vessels"][1]
            capability_check = _check_by_name(
                rigged,
                "rigging-capability-unsupported-package",
            )
            self.assertEqual(capability_check["kind"], "runtime-capability")
            self.assertTrue(capability_check["included"])
            self.assertIn("does not support", capability_check["failure_reason"])

    def test_preflight_dry_run_includes_agent_prompt_checks_when_enabled(self) -> None:
        config = AGENT_PREFLIGHT_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"\nrigging = ["agent-check"]',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path, logbook_dir, workspace_dir = _write_preflight_inputs(
                config,
                root,
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "preflight",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                        "--agent-preflight",
                        "pi",
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["agent_preflight"], "pi")
            rigged = payload["comparisons"][0]["vessels"][1]
            agent_check = _check_by_name(rigged, "agent-tool-smoke")
            self.assertTrue(agent_check["included"])
            self.assertEqual(
                agent_check["transcript_dir"],
                str(logbook_dir / "transcripts" / "baseline-vs-rigged" / "rigged"),
            )
            self.assertEqual(
                agent_check["artifact_path"],
                str(logbook_dir / "preflight" / "baseline-vs-rigged" / "rigged.json"),
            )


class CliResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


def _run_preflight(config: str, root: Path) -> tuple[CliResult, Path]:
    config_path, logbook_dir, workspace_dir = _write_preflight_inputs(config, root)

    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(
            [
                "preflight",
                str(config_path),
                "--logbook",
                str(logbook_dir),
                "--workspace",
                str(workspace_dir),
                "--secret",
                "token=test-secret",
            ]
        )

    result = CliResult(exit_code, stdout.getvalue(), stderr.getvalue())
    return result, logbook_dir


def _write_preflight_inputs(config: str, root: Path) -> tuple[Path, Path, Path]:
    config_path = root / "regatta.toml"
    logbook_dir = root / "logbook"
    workspace_dir = root / "workspace"
    config_path.write_text(config, encoding="utf-8")
    workspace_dir.mkdir()
    return config_path, logbook_dir, workspace_dir


def _check_by_name(artifact: dict[str, object], name: str) -> dict[str, object]:
    checks = (
        artifact["checks"] if "checks" in artifact else artifact["preflight_checks"]
    )
    assert isinstance(checks, list)
    for check in checks:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
