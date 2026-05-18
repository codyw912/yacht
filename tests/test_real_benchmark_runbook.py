import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main


class RealBenchmarkRunbookTests(unittest.TestCase):
    def test_real_benchmark_runbook_prints_commands_and_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-benchmark-runbook",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            runbook = json.loads(stdout.getvalue())
            self.assertEqual(runbook["schema"], "yacht.real-benchmark-runbook.v1")
            self.assertEqual(runbook["regatta"], "pi-fff-comparison")
            self.assertEqual(runbook["course"], "swe-bench-lite")
            self.assertEqual(runbook["agent"], "pi")
            self.assertEqual(
                runbook["secret_placeholders"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "argument": "--secret anthropic=@env:ANTHROPIC_API_KEY",
                    }
                ],
            )

            commands = {step["name"]: step["command"] for step in runbook["steps"]}
            self.assertIn(
                "uv run yacht real-benchmark-eval",
                commands["real-benchmark-eval"],
            )
            self.assertEqual(
                commands["real-benchmark-eval"],
                (
                    f"uv run yacht real-benchmark-eval {config_path} "
                    f"--logbook {logbook_dir} --workspace {workspace_path} "
                    "--secret anthropic=@env:ANTHROPIC_API_KEY "
                    "--max-workers 1 "
                    "--python-executable 'uv run --with swebench python'"
                ),
            )
            self.assertEqual(
                commands["benchmark-status"],
                f"uv run yacht benchmark-status --logbook {logbook_dir}",
            )
            self.assertEqual(
                commands["benchmark-report"],
                f"uv run yacht benchmark-report --logbook {logbook_dir}",
            )
            self.assertEqual(
                commands["benchmark-report-filtered"],
                (
                    f"uv run yacht benchmark-report --logbook {logbook_dir} "
                    "--vessel pi-plus-fff --task django__django-11099"
                ),
            )
            self.assertEqual(
                commands["benchmark-report-markdown"],
                (
                    f"uv run yacht benchmark-report --logbook {logbook_dir} "
                    f"--format markdown --output {logbook_dir / 'benchmark-report.md'}"
                ),
            )

            artifacts = runbook["artifacts"]
            self.assertEqual(
                artifacts["course_handoff"],
                str(logbook_dir / "course-handoff.json"),
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "preflight"
                    / "pi-vs-pi-fff"
                    / "pi-plus-fff.json"
                ),
                artifacts["preflight"],
            )
            self.assertEqual(
                artifacts["preflight_evidence_report"],
                str(logbook_dir / "preflight-evidence-report.json"),
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "task-attempts"
                    / "pi-vs-pi-fff"
                    / "pi-plus-fff"
                    / "django__django-11099.json"
                ),
                artifacts["task_attempts"],
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "course-handoff"
                    / "swe-bench"
                    / "vessels"
                    / "pi-plus-fff"
                    / "candidate-patches.jsonl"
                ),
                artifacts["candidate_patches"],
            )
            self.assertEqual(
                artifacts["runtime_instances"],
                str(logbook_dir / "runtime-instances.json"),
            )
            self.assertEqual(
                artifacts["benchmark_scorecard"],
                str(logbook_dir / "benchmark-scorecard.json"),
            )
            self.assertEqual(
                artifacts["benchmark_report"],
                str(logbook_dir / "benchmark-report.md"),
            )
            self.assertEqual(
                artifacts["real_benchmark_runbook"],
                str(logbook_dir / "real-benchmark-runbook.json"),
            )
            self.assertEqual(
                json.loads(
                    (logbook_dir / "real-benchmark-runbook.json").read_text(
                        encoding="utf-8"
                    )
                ),
                runbook,
            )

    def test_real_benchmark_runbook_can_print_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "real-benchmark-runbook",
                        str(config_path),
                        "--logbook",
                        str(logbook_dir),
                        "--workspace",
                        str(workspace_path),
                        "--format",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            markdown = stdout.getvalue()
            self.assertIn("## Real Benchmark Runbook", markdown)
            self.assertIn("Regatta: `pi-fff-comparison`", markdown)
            self.assertIn("### Commands", markdown)
            self.assertIn("```sh\nuv run yacht real-benchmark-eval", markdown)
            self.assertIn("--secret anthropic=@env:ANTHROPIC_API_KEY", markdown)
            self.assertIn("--vessel pi-plus-fff --task django__django-11099", markdown)
            self.assertIn("### Expected Artifacts", markdown)
            self.assertIn("logbook/preflight-evidence-report.json", markdown)
            self.assertIn("logbook/benchmark-scorecard.json", markdown)
            self.assertIn("logbook/benchmark-report.md", markdown)

            runbook = json.loads(
                (logbook_dir / "real-benchmark-runbook.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(runbook["schema"], "yacht.real-benchmark-runbook.v1")
            self.assertEqual(runbook["regatta"], "pi-fff-comparison")


if __name__ == "__main__":
    unittest.main()
