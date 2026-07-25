import json
import tempfile
import unittest
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.workflows.real_benchmark_runbook import (
    render_real_benchmark_runbook,
    write_real_benchmark_runbook,
)


class RealBenchmarkRunbookTests(unittest.TestCase):
    def test_real_benchmark_runbook_prints_commands_and_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()

            runbook = write_real_benchmark_runbook(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                max_workers=1,
            )

            self.assertEqual(runbook["schema"], "yacht.real-benchmark-runbook.v1")
            self.assertEqual(runbook["regatta"], "pi-fff-comparison")
            self.assertEqual(runbook["course"], "swe-bench-lite")
            self.assertEqual(runbook["agent"], "pi")
            self.assertEqual(
                runbook["surfaces"],
                {
                    "agent_harnesses": ["pi"],
                    "tools": ["fff"],
                    "benchmark": {
                        "name": "swe-bench-lite",
                        "adapter": "swe-bench",
                        "dataset": "princeton-nlp/SWE-bench_Lite",
                        "split": "test",
                        "execution_harness": "docker",
                    },
                },
            )
            self.assertEqual(
                runbook["rigging_capabilities"][1],
                {
                    "vessel": "pi-plus-fff",
                    "runtime": "pi",
                    "status": "supported",
                    "runtime_backend": "host-nix",
                    "runtime_harness": "pi",
                    "runtime_agent": "pi",
                    "supported_install_methods": [
                        "agent-extension",
                        "config-file",
                        "mcp-server",
                        "package",
                        "preinstalled",
                        "custom-command",
                    ],
                    "install_checks": [
                        {
                            "origin": "rigging",
                            "origin_name": "pi-fff",
                            "method": "agent-extension",
                            "target": "npm:@ff-labs/pi-fff",
                            "supported": True,
                        }
                    ],
                },
            )
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
                "uv run yacht run",
                commands["run"],
            )
            self.assertEqual(
                commands["run"],
                (
                    f"uv run yacht run {config_path} "
                    f"--logbook {logbook_dir} --workspace {workspace_path} "
                    "--secret anthropic=@env:ANTHROPIC_API_KEY "
                    "--max-workers 1"
                ),
            )
            self.assertEqual(
                commands["status"],
                f"uv run yacht status --logbook {logbook_dir}",
            )
            self.assertEqual(
                commands["report"],
                f"uv run yacht report --logbook {logbook_dir}",
            )
            self.assertEqual(
                commands["report-filtered"],
                (
                    f"uv run yacht report --logbook {logbook_dir} "
                    "--vessel pi-plus-fff --task django__django-11099"
                ),
            )
            self.assertEqual(
                commands["report-markdown"],
                (
                    f"uv run yacht report --logbook {logbook_dir} "
                    f"--format markdown --output {logbook_dir / 'benchmark-report.md'}"
                ),
            )

            artifacts = runbook["artifacts"]
            self.assertEqual(
                artifacts["course_handoff"],
                str(logbook_dir / "course-handoff.json"),
            )
            self.assertIn(
                str(logbook_dir / "preflight" / "pi-vs-pi-fff" / "pi-plus-fff.json"),
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

            markdown = render_real_benchmark_runbook(
                write_real_benchmark_runbook(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=workspace_path,
                    max_workers=1,
                )
            )
            self.assertIn("## Real Benchmark Runbook", markdown)
            self.assertIn("Regatta: `pi-fff-comparison`", markdown)
            self.assertIn("### Runtime Capabilities", markdown)
            self.assertIn("`pi-plus-fff`: `supported`", markdown)
            self.assertIn("### Commands", markdown)
            self.assertIn("```sh\nuv run yacht run", markdown)
            self.assertIn("--secret anthropic=@env:ANTHROPIC_API_KEY", markdown)
            self.assertNotIn("--python-executable", markdown)
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

    def test_real_benchmark_runbook_lists_small_task_set_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_path = root / "workspace"
            logbook_dir = root / "logbook"
            workspace_path.mkdir()

            runbook = write_real_benchmark_runbook(
                config_path=Path("examples/container-pi-fff-real-benchmark-small.toml"),
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                max_workers=1,
            )
            self.assertEqual(
                runbook["regatta"],
                "container-pi-fff-real-benchmark-small",
            )

            commands = {step["name"]: step["command"] for step in runbook["steps"]}
            self.assertIn(
                "--vessel pi-container-fff --task django__django-11099",
                commands["report-filtered"],
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "task-attempts"
                    / "container-pi-vs-pi-fff-benchmark-small"
                    / "pi-container-fff"
                    / "django__django-11099.json"
                ),
                runbook["artifacts"]["task_attempts"],
            )
            self.assertIn(
                str(
                    logbook_dir
                    / "task-attempts"
                    / "container-pi-vs-pi-fff-benchmark-small"
                    / "pi-container-fff"
                    / "django__django-11179.json"
                ),
                runbook["artifacts"]["task_attempts"],
            )


if __name__ == "__main__":
    unittest.main()
