import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.benchmark_status import build_benchmark_status
from yacht.benchmark_status import render_benchmark_status
from yacht.cli import main


class BenchmarkStatusTests(unittest.TestCase):
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
