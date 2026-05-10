import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from yacht.preflight import AgentPromptResult
from yacht.preflight_runner import run_preflight
from yacht.cli import main


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


class CliPreflightTests(unittest.TestCase):
    def test_preflight_writes_artifacts_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, logbook_dir = _run_preflight(PASSING_PREFLIGHT_CONFIG, Path(temp_dir))

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stderr, "")
            self.assertFalse((logbook_dir / "scorecard.json").exists())
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(
                summary["comparisons"][0],
                {
                    "name": "baseline-vs-rigged",
                    "status": "passed",
                    "vessels": [
                        {"name": "baseline", "status": "passed"},
                        {"name": "rigged", "status": "passed"},
                    ],
                },
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
                summary["comparisons"][0]["vessels"],
                [
                    {"name": "baseline", "status": "passed"},
                    {"name": "rigged", "status": "failed"},
                ],
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "rigged.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "failed")

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

            self.assertEqual(summary["status"], "passed")
            self.assertEqual(len(calls), 1)
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
    checks = artifact["checks"]
    assert isinstance(checks, list)
    for check in checks:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
