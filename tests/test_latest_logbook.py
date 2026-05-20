import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.latest_logbook import build_latest_logbook


class LatestLogbookTests(unittest.TestCase):
    def test_finds_latest_prefixed_benchmark_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            older = _write_logbook(root / "yacht-older", "benchmark-scorecard.json")
            latest = _write_logbook(
                root / "yacht-latest",
                "real-benchmark-repetitions.json",
            )
            _touch(older / "benchmark-scorecard.json", 1000)
            _touch(latest / "real-benchmark-repetitions.json", 2000)
            _write_logbook(root / "other-logbook", "benchmark-scorecard.json")

            report = build_latest_logbook(root)

            self.assertEqual(report["schema"], "yacht.latest-logbook.v1")
            self.assertEqual(report["status"], "found")
            self.assertEqual(report["logbook"], str(latest))
            self.assertEqual(report["kind"], "benchmark-repetitions")
            self.assertIn("real_benchmark_repetitions", report["artifacts"])
            self.assertEqual(
                report["next_steps"][0]["command_preview"],
                f"uv run yacht benchmark-status --logbook {latest}",
            )

    def test_latest_logbook_command_prints_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(root / "yacht-demo", "benchmark-scorecard.json")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["latest-logbook", "--root", str(root)])

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn(f"Latest logbook: {logbook}", report)
            self.assertIn("Kind: benchmark", report)
            self.assertIn(
                f"command: uv run yacht benchmark-report --logbook {logbook}",
                report,
            )

    def test_latest_logbook_command_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(root / "yacht-demo", "benchmark-aggregate.json")

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "latest-logbook",
                        "--root",
                        str(root),
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["logbook"], str(logbook))
            self.assertEqual(payload["kind"], "benchmark-repetitions")

    def test_latest_logbook_reports_missing_logbooks_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["latest-logbook", "--root", temp_dir])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: no YACHT benchmark logbooks found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())


def _write_logbook(path: Path, artifact_name: str) -> Path:
    path.mkdir(parents=True)
    (path / artifact_name).write_text('{"status": "complete"}\n', encoding="utf-8")
    return path


def _touch(path: Path, timestamp: int) -> None:
    os.utime(path, (timestamp, timestamp))


if __name__ == "__main__":
    unittest.main()
