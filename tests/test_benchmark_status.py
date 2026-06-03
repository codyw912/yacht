import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.logbook.index import RUN_INDEX_PATH
from yacht.reports.benchmark_status import build_benchmark_status
from yacht.reports.benchmark_status import render_benchmark_status


class BenchmarkStatusTests(unittest.TestCase):
    def test_prefers_run_index_artifact_list_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "preflight-evidence-report.json").write_text(
                json.dumps({"status": "ready"}),
                encoding="utf-8",
            )
            (logbook_dir / RUN_INDEX_PATH).write_text(
                json.dumps(
                    {
                        "schema": "yacht.run-index.v1",
                        "run_kind": "real-benchmark",
                        "status": "partial",
                        "updated_at": "2026-06-03T12:00:00Z",
                        "config_path": "/tmp/regatta.toml",
                        "logbook": str(logbook_dir),
                        "regatta": "demo",
                        "course": "course",
                        "comparisons": [
                            {
                                "name": "comparison",
                                "course": "course",
                                "vessels": ["baseline", "challenger"],
                            }
                        ],
                        "artifacts": {
                            "preflight_evidence_report": {
                                "path": str(
                                    logbook_dir / "preflight-evidence-report.json"
                                ),
                                "present": True,
                            },
                            "benchmark_scorecard": {
                                "path": str(logbook_dir / "benchmark-scorecard.json"),
                                "present": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = build_benchmark_status(logbook_dir)

            self.assertEqual(status["status"], "partial")
            self.assertEqual(status["run_kind"], "real-benchmark")
            self.assertEqual(status["regatta"], "demo")
            self.assertEqual(status["course"], "course")
            self.assertEqual(
                status["comparisons"][0]["vessels"],
                ["baseline", "challenger"],
            )
            self.assertEqual(
                [artifact["label"] for artifact in status["artifacts"]],
                ["preflight evidence report", "benchmark scorecard"],
            )
            self.assertEqual(status["artifacts"][0]["state"], "ready")
            self.assertEqual(status["artifacts"][1]["state"], "missing")

    def test_reports_missing_artifacts_and_start_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            status = build_benchmark_status(logbook_dir)

            self.assertEqual(status["status"], "empty")
            self.assertEqual(status["artifacts"][0]["state"], "missing")
            self.assertEqual(status["next_steps"][0]["label"], "Run real benchmark eval")
            self.assertEqual(
                status["next_steps"][0]["command"][:4],
                ["uv", "run", "yacht", "real-benchmark-eval"],
            )

    def test_uses_real_benchmark_eval_next_steps_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "real-benchmark-eval.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "next_steps": [
                            {
                                "label": "Rerun benchmark launch",
                                "reason": "native reports are missing",
                                "command": [
                                    "uv",
                                    "run",
                                    "yacht",
                                    "benchmark-launch",
                                    "--logbook",
                                    str(logbook_dir),
                                ],
                                "command_preview": (
                                    f"uv run yacht benchmark-launch --logbook "
                                    f"{logbook_dir}"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = render_benchmark_status(logbook_dir)

            self.assertIn("Benchmark status:", report)
            self.assertIn("blocked | real benchmark eval", report)
            self.assertIn("1. Rerun benchmark launch", report)
            self.assertIn(
                f"command: uv run yacht benchmark-launch --logbook {logbook_dir}",
                report,
            )

    def test_renders_surface_summary_when_real_benchmark_eval_is_available(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "real-benchmark-eval.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "surfaces": {
                            "agent_harnesses": ["pi"],
                            "tools": ["fff"],
                            "benchmark": {
                                "adapter": "swe-bench",
                                "dataset": "princeton-nlp/SWE-bench_Lite",
                                "split": "test",
                                "execution_harness": "docker",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = render_benchmark_status(logbook_dir)

            self.assertIn(
                "Surfaces: agents=pi | tools=fff | "
                "benchmark=swe-bench/princeton-nlp/SWE-bench_Lite/test/docker",
                report,
            )

    def test_reports_invalid_artifacts_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "benchmark-scorecard.json").write_text(
                "{not json",
                encoding="utf-8",
            )

            status = build_benchmark_status(logbook_dir)

            self.assertEqual(status["status"], "invalid")
            scorecard = status["artifacts"][-1]
            self.assertEqual(scorecard["state"], "invalid")
            self.assertIn("invalid JSON", scorecard["detail"])

    def test_uses_scorecard_filtered_inspection_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / "real-benchmark-eval.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "next_steps": [
                            {
                                "label": "Render benchmark report",
                                "reason": "Older summary next step.",
                                "command": [
                                    "uv",
                                    "run",
                                    "yacht",
                                    "benchmark-report",
                                    "--logbook",
                                    str(logbook_dir),
                                ],
                                "command_preview": (
                                    "uv run yacht benchmark-report --logbook "
                                    f"{logbook_dir}"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (logbook_dir / "benchmark-scorecard.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "next_steps": [
                            {
                                "label": "Inspect filtered benchmark details",
                                "reason": "Inspect one vessel/task.",
                                "command": [
                                    "uv",
                                    "run",
                                    "yacht",
                                    "benchmark-report",
                                    "--logbook",
                                    str(logbook_dir),
                                    "--vessel",
                                    "pi-plus-fff",
                                    "--task",
                                    "django__django-11099",
                                ],
                                "command_preview": (
                                    "uv run yacht benchmark-report --logbook "
                                    f"{logbook_dir} --vessel pi-plus-fff --task "
                                    "django__django-11099"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = render_benchmark_status(logbook_dir)

            self.assertIn("1. Inspect filtered benchmark details", report)
            self.assertIn("--vessel pi-plus-fff --task django__django-11099", report)

    def test_benchmark_status_command_writes_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            output_path = root / "reports" / "benchmark-status.md"

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark-status",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "markdown",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "## Benchmark status",
                output_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
