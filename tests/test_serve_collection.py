import tempfile
import json
import unittest
from pathlib import Path

from tests.test_benchmark_aggregate import _write_logbook
from yacht.serve.collection import collect_vessel_records, discover_logbooks
from yacht.reports.benchmark_report import render_benchmark_report
from yacht.reports.benchmark_status import build_benchmark_status
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

    def test_skips_unreadable_directories_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            locked = root / "locked"
            locked.mkdir()
            locked.chmod(0o000)
            try:
                entries = discover_logbooks(root)
            finally:
                locked.chmod(0o755)

            self.assertEqual(
                [entry.logbook.name for entry in entries],
                ["run-1"],
            )

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

    def test_smoke_dashboard_status_uses_readiness_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "smoke"
            logbook.mkdir()
            (logbook / "run-index.json").write_text(
                json.dumps(
                    {
                        "schema": "yacht.run-index.v2",
                        "run_kind": "real-smoke",
                        "status": "complete",
                        "stage": "complete",
                        "started_at": "2026-08-19T00:00:00Z",
                        "updated_at": "2026-08-19T00:01:00Z",
                        "terminal_at": "2026-08-19T00:01:00Z",
                        "config_path": "/tmp/regatta.toml",
                        "regatta": "smoke-regatta",
                        "course": "local-smoke",
                        "comparisons": [],
                        "artifacts": {
                            "smoke_readiness_report": {
                                "path": "smoke-readiness-report.json",
                                "present": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (logbook / "smoke-readiness-report.json").write_text(
                json.dumps(
                    {
                        "schema": "yacht.smoke-readiness-report.v1",
                        "regatta": "smoke-regatta",
                        "course": "local-smoke",
                        "status": "ready",
                        "summary": {
                            "total_vessels": 1,
                            "ready_vessels": 1,
                            "blocked_vessels": 0,
                            "passed_preflight_vessels": 1,
                            "completed_task_attempt_vessels": 1,
                            "passed_agent_prompt_checks": 0,
                        },
                        "comparisons": [
                            {
                                "name": "smoke",
                                "status": "ready",
                                "vessels": [
                                    {
                                        "name": "local",
                                        "status": "ready",
                                        "preflight_status": "passed",
                                        "task_attempt_status": "measured",
                                        "preflight_artifact_path": "preflight.json",
                                        "task_attempt_artifact_paths": ["attempt.json"],
                                        "agent_prompt_checks": {
                                            "total": 0,
                                            "passed": 0,
                                        },
                                        "attempts_by_tool": {},
                                        "expected_tool_calls": [],
                                        "missing_expected_tool_calls": [],
                                        "reasons": [],
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            entries = discover_logbooks(root)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].status, "complete")
            self.assertEqual(entries[0].outcome, "ready")
            self.assertEqual(entries[0].errors, ())

    def test_reader_resolves_moved_indexed_scorecards_for_report_and_dashboard(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(
                root / "run-1",
                baseline_resolved=1,
                fff_resolved=1,
            )
            artifacts = logbook / "artifacts"
            artifacts.mkdir()
            benchmark = logbook / "benchmark-scorecard.json"
            attempts = logbook / "task-attempt-scorecard.json"
            benchmark.rename(artifacts / benchmark.name)
            attempts.rename(artifacts / attempts.name)
            wake = artifacts / "real-benchmark-eval.json"
            wake.write_text(
                json.dumps(
                    {
                        "surfaces": {
                            "agent_harnesses": ["omp"],
                            "tools": ["agent-skill"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            _write_v2_index(
                logbook,
                {
                    "benchmark_scorecard": "artifacts/benchmark-scorecard.json",
                    "task_attempt_scorecard": "artifacts/task-attempt-scorecard.json",
                    "real_benchmark_eval": "artifacts/real-benchmark-eval.json",
                },
            )

            entries = discover_logbooks(root)
            report = render_benchmark_report(logbook)
            html = render_benchmark_report(logbook, output_format="html")
            status = build_benchmark_status(logbook)

            self.assertEqual(len(entries), 1)
            self.assertIsNotNone(entries[0].benchmark_scorecard)
            self.assertIsNotNone(entries[0].attempt_scorecard)
            self.assertIn("Benchmark scorecard:", report)
            self.assertIn(
                str((artifacts / "benchmark-scorecard.json").resolve()),
                report,
            )
            self.assertIn(str((artifacts / "benchmark-scorecard.json").resolve()), html)
            self.assertEqual(status["surfaces"]["agent_harnesses"], ["omp"])

    def test_partial_indexed_logbook_keeps_lifecycle_and_missing_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "run-1"
            logbook.mkdir()
            _write_v2_index(
                logbook,
                {"benchmark_scorecard": "artifacts/benchmark-scorecard.json"},
                status="running",
            )

            entries = discover_logbooks(root)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].status, "running")
            self.assertEqual(entries[0].errors, ())
            self.assertEqual(
                entries[0].missing_artifacts,
                (
                    "benchmark_scorecard: "
                    f"{(logbook / 'artifacts/benchmark-scorecard.json').resolve()}",
                ),
            )

    def test_malformed_present_index_prevents_scorecard_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(
                root / "run-1",
                baseline_resolved=1,
                fff_resolved=1,
            )
            (logbook / "run-index.json").write_text(
                '{"schema": "yacht.run-index.v2"}\n',
                encoding="utf-8",
            )

            entries = discover_logbooks(root)

            self.assertEqual(len(entries), 1)
            self.assertIsNone(entries[0].benchmark_scorecard)
            self.assertIsNone(entries[0].attempt_scorecard)
            self.assertIn("run index", entries[0].errors[0])

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


def _write_v2_index(
    logbook: Path,
    artifacts: dict[str, str],
    *,
    status: str = "complete",
) -> None:
    document = {
        "schema": "yacht.run-index.v2",
        "run_kind": "real-benchmark",
        "status": status,
        "stage": "complete" if status == "complete" else "launch",
        "started_at": "2026-08-19T00:00:00Z",
        "updated_at": "2026-08-19T00:01:00Z",
        "config_path": "/tmp/regatta.toml",
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "comparisons": [],
        "artifacts": {
            name: {"path": path, "present": True} for name, path in artifacts.items()
        },
    }
    if status == "complete":
        document["terminal_at"] = "2026-08-19T00:01:00Z"
    (logbook / "run-index.json").write_text(
        json.dumps(document),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
