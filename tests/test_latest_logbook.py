import json
import os
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import ConfigError
from yacht.reports.latest_logbook import build_latest_logbook
from yacht.reports.latest_logbook import render_latest_logbook


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
                f"uv run yacht status --logbook {latest}",
            )

    def test_latest_logbook_command_prints_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(root / "yacht-demo", "benchmark-scorecard.json")

            report = render_latest_logbook(root)

            self.assertIn(f"Latest logbook: {logbook}", report)
            self.assertIn("Kind: benchmark", report)
            self.assertIn(
                f"command: uv run yacht report --logbook {logbook}",
                report,
            )

    def test_latest_logbook_command_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(root / "yacht-demo", "benchmark-aggregate.json")

            payload = json.loads(render_latest_logbook(root, output_format="json"))
            self.assertEqual(payload["logbook"], str(logbook))
            self.assertEqual(payload["kind"], "benchmark-repetitions")

    def test_malformed_index_is_authoritative_over_legacy_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(
                root / "yacht-broken",
                "benchmark-scorecard.json",
            )
            (logbook / "run-index.json").write_text(
                '{"schema": "yacht.run-index.v2"}\n',
                encoding="utf-8",
            )

            report = build_latest_logbook(root)

            self.assertEqual(report["logbook"], str(logbook))
            self.assertEqual(report["kind"], "broken")
            self.assertEqual(
                set(report["artifacts"]),
                {"run_index"},
            )

    def test_latest_logbook_reports_missing_logbooks_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                ConfigError,
                "no YACHT benchmark logbooks found",
            ):
                render_latest_logbook(Path(temp_dir))


def _write_logbook(path: Path, artifact_name: str) -> Path:
    path.mkdir(parents=True)
    (path / artifact_name).write_text('{"status": "complete"}\n', encoding="utf-8")
    return path


def _touch(path: Path, timestamp: int) -> None:
    os.utime(path, (timestamp, timestamp))


if __name__ == "__main__":
    unittest.main()
