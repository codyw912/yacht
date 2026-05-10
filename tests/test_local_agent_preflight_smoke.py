import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.preflight import AgentPromptResult
from yacht.preflight_runner import run_preflight
from yacht.regatta import load_regatta


class LocalAgentPreflightSmokeTests(unittest.TestCase):
    def test_example_runs_full_agent_preflight_with_injected_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()
            calls = []

            def runner_factory(instance, transcript_dir):
                def runner(prompt, env, cwd):
                    calls.append((prompt, env, cwd, transcript_dir))
                    return AgentPromptResult(
                        exit_code=0,
                        response='{"available": true, "configured": true}',
                        tool_calls=("local-smoke",),
                        transcript_path=transcript_dir / "local-agent-smoke.json",
                    )

                return runner

            summary = run_preflight(
                Path("examples/local-agent-preflight-smoke.toml"),
                logbook_dir,
                workspace_dir,
                {},
                agent_prompt_runner_factory=runner_factory,
            )

            self.assertEqual(summary["status"], "passed")
            baseline = summary["comparisons"][0]["vessels"][0]
            self.assertEqual(baseline["name"], "local-baseline")
            self.assertEqual(
                [(check["name"], check["status"]) for check in baseline["checks"]],
                [("runtime-home-isolated", "passed")],
            )
            vessel = summary["comparisons"][0]["vessels"][1]
            self.assertEqual(vessel["name"], "local-agent-with-tool")
            self.assertEqual(
                [(check["name"], check["status"]) for check in vessel["checks"]],
                [
                    ("runtime-home-isolated", "passed"),
                    ("local-tool-mode", "passed"),
                    ("local-tool-state-isolated", "passed"),
                    ("local-agent-smoke", "passed"),
                ],
            )
            self.assertEqual(calls[0][0], "preflights/local-agent-smoke.md")
            self.assertEqual(calls[0][1]["LOCAL_TOOL_MODE"], "required")
            self.assertEqual(calls[0][2], workspace_dir)
            self.assertEqual(
                calls[0][3],
                logbook_dir
                / "transcripts"
                / "local-agent-preflight"
                / "local-agent-with-tool",
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "local-agent-preflight"
                / "local-agent-with-tool.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            agent_check = _check_by_name(artifact, "local-agent-smoke")
            self.assertEqual(agent_check["status"], "passed")
            self.assertEqual(agent_check["evidence"]["tool_calls"], ["local-smoke"])
            self.assertEqual(
                agent_check["evidence"]["response_json"],
                {"available": True, "configured": True},
            )

    def test_cli_runs_example_with_local_smoke_agent_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "preflight",
                        "examples/local-agent-preflight-smoke.toml",
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                        "--agent-preflight",
                        "local-smoke",
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "passed")
            rigged = summary["comparisons"][0]["vessels"][1]
            agent_check = _check_by_name(rigged, "local-agent-smoke")
            self.assertEqual(agent_check["status"], "passed")

            transcript_path = (
                logbook_dir
                / "transcripts"
                / "local-agent-preflight"
                / "local-agent-with-tool"
                / "local-smoke-agent.json"
            )
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            self.assertEqual(transcript["prompt"], "preflights/local-agent-smoke.md")
            self.assertEqual(transcript["tool_calls"], ["local-smoke"])
            self.assertEqual(transcript["env"]["LOCAL_TOOL_MODE"], "required")

    def test_cli_dry_run_includes_local_smoke_agent_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "preflight",
                        "examples/local-agent-preflight-smoke.toml",
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_dir),
                        "--agent-preflight",
                        "local-smoke",
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            plan = json.loads(stdout.getvalue())
            self.assertEqual(plan["agent_preflight"], "local-smoke")
            rigged = plan["comparisons"][0]["vessels"][1]
            agent_check = _check_by_name(rigged, "local-agent-smoke")
            self.assertTrue(agent_check["included"])
            self.assertEqual(
                agent_check["transcript_dir"],
                str(
                    logbook_dir
                    / "transcripts"
                    / "local-agent-preflight"
                    / "local-agent-with-tool"
                ),
            )

    def test_example_prompt_path_exists(self) -> None:
        regatta = load_regatta(Path("examples/local-agent-preflight-smoke.toml"))
        prompts = [
            check.prompt
            for rigging in regatta.rigging_recipes.values()
            for check in rigging.preflight.checks
            if check.kind == "agent-prompt"
        ]

        self.assertEqual(prompts, ["preflights/local-agent-smoke.md"])
        self.assertTrue(Path(prompts[0]).is_file())


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
