import tempfile
import unittest
from pathlib import Path

from tests.test_benchmark_aggregate import _write_logbook
from yacht.serve.collection import collect_vessel_records, discover_logbooks
from yacht.domain.model import ConfigError


class DiscoverLogbooksTests(unittest.TestCase):
    def test_finds_logbooks_one_level_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            _write_logbook(root / "run-2", baseline_resolved=0, fff_resolved=1)
            (root / "not-a-logbook").mkdir()

            entries = discover_logbooks(root)

            self.assertEqual(
                sorted(entry.logbook.name for entry in entries),
                ["run-1", "run-2"],
            )
            for entry in entries:
                self.assertEqual(entry.regatta, "pi-fff-comparison")
                self.assertEqual(entry.course, "swe-bench-lite")
                self.assertEqual(entry.errors, ())
                self.assertIsNotNone(entry.benchmark_scorecard)
                self.assertIsNotNone(entry.attempt_scorecard)

    def test_root_itself_can_be_a_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "inner", baseline_resolved=1, fff_resolved=1).rename(
                root / "moved"
            )
            logbook = root / "moved"
            for artifact in logbook.iterdir():
                artifact.rename(root / artifact.name)

            entries = discover_logbooks(root)

            self.assertEqual([entry.logbook for entry in entries], [root])

    def test_broken_artifacts_yield_error_entries_not_silence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            broken = root / "broken"
            broken.mkdir()
            (broken / "benchmark-scorecard.json").write_text(
                "not json", encoding="utf-8"
            )

            entries = discover_logbooks(root)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].logbook, broken)
            self.assertEqual(len(entries[0].errors), 1)
            self.assertIn("not valid JSON", entries[0].errors[0])
            self.assertIsNone(entries[0].benchmark_scorecard)

    def test_invalid_scorecard_schema_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            invalid = root / "invalid"
            invalid.mkdir()
            (invalid / "task-attempt-scorecard.json").write_text(
                '{"schema": "yacht.task-attempt-scorecard.v1"}',
                encoding="utf-8",
            )

            entries = discover_logbooks(root)

            self.assertEqual(len(entries), 1)
            self.assertIn("invalid", entries[0].errors[0])

    def test_rejects_missing_root(self) -> None:
        with self.assertRaisesRegex(ConfigError, "not a directory"):
            discover_logbooks(Path("/nonexistent/dashboard/root"))


class CollectVesselRecordsTests(unittest.TestCase):
    def test_flattens_scorecards_into_vessel_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(
                root / "run-1",
                baseline_resolved=1,
                fff_resolved=1,
                harness_version="0.74.0",
            )
            _write_logbook(
                root / "run-2",
                baseline_resolved=0,
                fff_resolved=1,
                harness_version="0.75.0",
            )

            records = collect_vessel_records(discover_logbooks(root))

            self.assertEqual(len(records), 4)
            record = next(
                item
                for item in records
                if item.vessel == "pi-baseline" and item.logbook.endswith("run-1")
            )
            self.assertEqual(record.regatta, "pi-fff-comparison")
            self.assertEqual(record.comparison, "pi-vs-pi-fff")
            self.assertEqual(record.usage["total_tokens"], 1000)
            self.assertEqual(record.outcome["resolved_instances"], 1)
            assert record.provenance is not None
            self.assertEqual(record.provenance["harness"]["version"], "0.74.0")

    def test_records_skip_logbooks_without_attempt_scorecards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(
                root / "run-1", baseline_resolved=1, fff_resolved=1
            )
            (logbook / "task-attempt-scorecard.json").unlink()

            entries = discover_logbooks(root)
            records = collect_vessel_records(entries)

            self.assertEqual(len(entries), 1)
            self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
