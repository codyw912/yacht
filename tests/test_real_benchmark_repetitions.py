import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.test_benchmark_aggregate import _write_logbook
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.logbook.index import require_logbook
from yacht.serve.collection import collect_vessel_records, discover_logbooks
from yacht.serve.server import respond
from yacht.reports.benchmark_status import render_benchmark_status
from yacht.cli import main
from yacht.workflows.real_benchmark_repetitions import run_real_benchmark_repetitions
from yacht.domain.model import ConfigError


class RealBenchmarkRepetitionsTests(unittest.TestCase):
    def test_runs_repetitions_into_child_logbooks_and_writes_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path = root / "workspace"
            workspace_path.mkdir()
            logbook_dir = root / "series"
            child_logbooks = []

            def eval_runner(child_logbook: Path) -> dict[str, object]:
                child_logbooks.append(child_logbook)
                resolved = 1 if child_logbook.name == "run-001" else 0
                _write_logbook(
                    child_logbook,
                    baseline_resolved=resolved,
                    fff_resolved=1,
                )
                return {
                    "status": "complete",
                    "regatta": "pi-fff-comparison",
                    "course": "swe-bench-lite",
                }

            summary = run_real_benchmark_repetitions(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                secret_values={},
                repetitions=2,
                eval_runner=eval_runner,
            )

            self.assertEqual(summary["schema"], "yacht.real-benchmark-repetitions.v1")
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(
                summary["surfaces"],
                {
                    "agent_harnesses": ["pi"],
                    "benchmark": {
                        "adapter": "swe-bench",
                        "dataset": "princeton-nlp/SWE-bench_Lite",
                        "execution_harness": "docker",
                        "name": "swe-bench-lite",
                        "split": "test",
                    },
                    "tools": ["fff"],
                },
            )
            self.assertEqual(summary["summary"]["repetitions"], 2)
            self.assertEqual(summary["summary"]["completed_runs"], 2)
            self.assertEqual(
                child_logbooks,
                [logbook_dir / "runs/run-001", logbook_dir / "runs/run-002"],
            )
            self.assertTrue((logbook_dir / "real-benchmark-repetitions.json").is_file())
            self.assertTrue((logbook_dir / "benchmark-aggregate.json").is_file())
            report_path = logbook_dir / "benchmark-report.md"
            self.assertTrue(report_path.is_file())
            self.assertIn(
                "## Benchmark aggregate",
                report_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                summary["artifacts"]["benchmark_report_markdown"],
                str(report_path),
            )
            self.assertNotIn("aggregate", summary)
            aggregate_summary = summary["aggregate_summary"]
            self.assertEqual(aggregate_summary["run_count"], 2)
            self.assertEqual(
                aggregate_summary["comparisons"][0]["delta"][
                    "resolved_instances_delta"
                ],
                1,
            )
            aggregate = json.loads(
                (logbook_dir / "benchmark-aggregate.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                aggregate["comparisons"][0]["delta"]["resolved_instances_delta"],
                1,
            )
            index = json.loads(
                (logbook_dir / "run-index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(index["run_kind"], "benchmark-repetitions")
            self.assertEqual(index["status"], "complete")
            self.assertEqual(
                index["children"],
                [
                    {"path": "runs/run-001", "status": "complete"},
                    {"path": "runs/run-002", "status": "complete"},
                ],
            )
            self.assertEqual(
                index["artifacts"],
                {
                    "real_benchmark_repetitions": {
                        "path": "real-benchmark-repetitions.json",
                        "present": True,
                    },
                    "benchmark_aggregate": {
                        "path": "benchmark-aggregate.json",
                        "present": True,
                    },
                    "benchmark_report_markdown": {
                        "path": "benchmark-report.md",
                        "present": True,
                    },
                },
            )

    def test_aggregates_moved_indexed_child_scorecards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            logbook_dir = root / "series"

            def eval_runner(child_logbook: Path) -> dict[str, object]:
                _write_logbook(
                    child_logbook,
                    baseline_resolved=1,
                    fff_resolved=1,
                )
                artifacts = child_logbook / "artifacts"
                artifacts.mkdir()
                for filename in (
                    "benchmark-scorecard.json",
                    "task-attempt-scorecard.json",
                ):
                    (child_logbook / filename).rename(artifacts / filename)
                (child_logbook / "run-index.json").write_text(
                    json.dumps(
                        {
                            "schema": "yacht.run-index.v2",
                            "run_kind": "real-benchmark",
                            "status": "complete",
                            "stage": "complete",
                            "started_at": "2026-08-19T00:00:00Z",
                            "updated_at": "2026-08-19T00:01:00Z",
                            "terminal_at": "2026-08-19T00:01:00Z",
                            "config_path": "/tmp/regatta.toml",
                            "regatta": "pi-fff-comparison",
                            "course": "swe-bench-lite",
                            "comparisons": [],
                            "artifacts": {
                                "benchmark_scorecard": {
                                    "path": "artifacts/benchmark-scorecard.json",
                                    "present": True,
                                },
                                "task_attempt_scorecard": {
                                    "path": "artifacts/task-attempt-scorecard.json",
                                    "present": True,
                                },
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return {"status": "complete"}

            summary = run_real_benchmark_repetitions(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root,
                secret_values={},
                repetitions=1,
                eval_runner=eval_runner,
            )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["aggregate_summary"]["run_count"], 1)
            self.assertEqual(
                summary["runs"][0]["artifacts"]["benchmark_scorecard"],
                str(
                    (
                        logbook_dir / "runs/run-001/artifacts/benchmark-scorecard.json"
                    ).resolve()
                ),
            )
            index = json.loads(
                (logbook_dir / "run-index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                index["children"],
                [{"path": "runs/run-001", "status": "complete"}],
            )

    def test_aggregates_completed_repetitions_when_one_child_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            logbook_dir = root / "series"

            def eval_runner(child_logbook: Path) -> dict[str, object]:
                if child_logbook.name == "run-001":
                    _write_logbook(
                        child_logbook,
                        baseline_resolved=1,
                        fff_resolved=1,
                    )
                    return {"status": "complete"}
                child_logbook.mkdir(parents=True)
                return {"status": "blocked"}

            summary = run_real_benchmark_repetitions(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root,
                secret_values={},
                repetitions=2,
                eval_runner=eval_runner,
            )

            self.assertEqual(summary["status"], "partial")
            self.assertEqual(summary["summary"]["completed_runs"], 1)
            self.assertEqual(summary["summary"]["failed_runs"], 1)
            self.assertEqual(summary["aggregate_summary"]["run_count"], 1)
            self.assertNotIn("aggregate", summary)
            index = json.loads(
                (logbook_dir / "run-index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(index["status"], "blocked")
            self.assertEqual(
                index["children"],
                [
                    {"path": "runs/run-001", "status": "complete"},
                    {"path": "runs/run-002", "status": "blocked"},
                ],
            )

    def test_child_exception_records_parent_and_child_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            logbook_dir = root / "series"

            def fail(child_logbook: Path) -> dict[str, object]:
                child_logbook.mkdir(parents=True)
                raise RuntimeError("child failed")

            with self.assertRaisesRegex(RuntimeError, "child failed"):
                run_real_benchmark_repetitions(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=root,
                    secret_values={},
                    repetitions=1,
                    eval_runner=fail,
                )

            index = json.loads(
                (logbook_dir / "run-index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(index["status"], "failed")
            self.assertEqual(
                index["children"],
                [{"path": "runs/run-001", "status": "failed"}],
            )

    def test_benchmark_status_recognizes_repetition_parent_logbooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _write_repetition_series(Path(temp_dir))

            report = render_benchmark_status(logbook_dir)

            self.assertIn("Benchmark status:", report)
            self.assertIn(
                "Surfaces: agents=pi | tools=fff | "
                "benchmark=swe-bench/princeton-nlp/SWE-bench_Lite/test/docker",
                report,
            )
            self.assertIn("complete | real benchmark repetitions", report)
            self.assertIn("present | benchmark aggregate", report)
            self.assertIn("1. Render benchmark report", report)
            self.assertIn(f"uv run yacht report --logbook {logbook_dir}", report)

    def test_moved_parent_discovers_children_once_and_reports_missing_child(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = _write_repetition_series(root)
            moved = root / "moved"
            original.rename(moved)

            snapshot = require_logbook(moved)
            self.assertEqual(
                [child.path for child in snapshot.children],
                [
                    (moved / "runs/run-001").resolve(),
                    (moved / "runs/run-002").resolve(),
                ],
            )
            entries = discover_logbooks(root)
            self.assertEqual(len(entries), 3)
            self.assertEqual(len(collect_vessel_records(entries)), 4)
            child_status, child_page = respond(
                root,
                "/logbook/moved/runs/run-001",
            )
            self.assertEqual(child_status, 200)
            self.assertIn("pi-fff-comparison", child_page)

            shutil.rmtree(moved / "runs/run-002")

            status_report = render_benchmark_status(moved)
            entries = discover_logbooks(root)
            self.assertIn("Status: blocked", status_report)
            self.assertIn("complete | no |", status_report)
            self.assertEqual(len(entries), 2)
            self.assertEqual(len(collect_vessel_records(entries)), 2)
            parent_status, parent_page = respond(root, "/logbook/moved")
            self.assertEqual(parent_status, 200)
            self.assertIn("Child Logbooks", parent_page)
            self.assertIn("recorded complete; missing", parent_page)

    def test_benchmark_report_renders_repetition_parent_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _write_repetition_series(Path(temp_dir))

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn(
                "Benchmark aggregate: pi-fff-comparison / swe-bench-lite", report
            )
            self.assertIn("Runs: 2", report)
            self.assertIn("Aggregate deltas:", report)

    def test_benchmark_report_rejects_filters_for_repetition_parent_aggregate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _write_repetition_series(Path(temp_dir))
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "repeated-run aggregate reports cannot be filtered",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_requires_positive_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text('name = "empty"\n', encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "real benchmark repetitions must be at least 1",
            ):
                run_real_benchmark_repetitions(
                    config_path=config_path,
                    logbook_dir=root / "series",
                    workspace_path=root,
                    secret_values={},
                    repetitions=0,
                    eval_runner=lambda _logbook: {"status": "complete"},
                )

    def test_requires_fresh_child_logbooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            logbook_dir = root / "series"
            (logbook_dir / "runs/run-001").mkdir(parents=True)

            with self.assertRaisesRegex(
                ConfigError,
                "repetition child logbook already exists",
            ):
                run_real_benchmark_repetitions(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=root,
                    secret_values={},
                    repetitions=1,
                    eval_runner=lambda _logbook: {"status": "complete"},
                )

    def test_command_reports_config_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with (
                patch(
                    "yacht.cli.commands.regatta.configured_harness_name",
                    return_value="pi",
                ),
                patch(
                    "yacht.cli.commands.regatta.run_real_benchmark_repetitions",
                    side_effect=ConfigError("boom"),
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    [
                        "run",
                        str(config_path),
                        "--logbook",
                        str(root / "series"),
                        "--workspace",
                        str(root),
                        "--repetitions",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("error: invalid regatta config: boom", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_command_prints_progress_to_stderr_without_polluting_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            def fake_runner(**kwargs):
                kwargs["progress"]("mock progress")
                return {
                    "schema": "yacht.real-benchmark-repetitions.v1",
                    "status": "complete",
                    "regatta": "pi-fff-comparison",
                    "course": "swe-bench-lite",
                    "summary": {
                        "repetitions": 2,
                        "completed_runs": 2,
                        "failed_runs": 0,
                        "aggregate_logbooks": 2,
                    },
                }

            with (
                patch(
                    "yacht.cli.commands.regatta.run_real_benchmark_repetitions",
                    side_effect=fake_runner,
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    [
                        "run",
                        str(config_path),
                        "--logbook",
                        str(root / "series"),
                        "--workspace",
                        str(root),
                        "--repetitions",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn(
                "Real benchmark repetitions: pi-fff-comparison / swe-bench-lite",
                report,
            )
            self.assertIn("Status: complete", report)
            self.assertIn("Runs: 2 | completed=2 | failed=0 | aggregated=2", report)
            self.assertEqual(stderr.getvalue(), "yacht: mock progress\n")

    def test_command_prints_json_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            stdout = StringIO()

            with (
                patch(
                    "yacht.cli.commands.regatta.run_real_benchmark_repetitions",
                    return_value={
                        "schema": "yacht.real-benchmark-repetitions.v1",
                        "status": "complete",
                        "regatta": "pi-fff-comparison",
                        "course": "swe-bench-lite",
                        "summary": {
                            "repetitions": 2,
                            "completed_runs": 2,
                            "failed_runs": 0,
                            "aggregate_logbooks": 2,
                        },
                    },
                ),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "run",
                        str(config_path),
                        "--logbook",
                        str(root / "series"),
                        "--workspace",
                        str(root),
                        "--repetitions",
                        "2",
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["summary"]["completed_runs"], 2)


def _write_repetition_series(root: Path) -> Path:
    config_path = root / "regatta.toml"
    config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
    logbook_dir = root / "series"

    def eval_runner(child_logbook: Path) -> dict[str, object]:
        resolved = 1 if child_logbook.name == "run-001" else 0
        _write_logbook(
            child_logbook,
            baseline_resolved=resolved,
            fff_resolved=1,
        )
        return {"status": "complete"}

    run_real_benchmark_repetitions(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=root,
        secret_values={},
        repetitions=2,
        eval_runner=eval_runner,
    )
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
