import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.reports.benchmark_aggregate import build_benchmark_aggregate
from yacht.cli import main
from yacht.domain.model import ConfigError


class BenchmarkAggregateTests(unittest.TestCase):
    def test_build_benchmark_aggregate_summarizes_repeated_logbooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            second = _write_logbook(root / "run-2", baseline_resolved=0, fff_resolved=1)

            aggregate = build_benchmark_aggregate([first, second])

            self.assertEqual(aggregate["schema"], "yacht.benchmark-aggregate.v1")
            self.assertEqual(aggregate["regatta"], "pi-fff-comparison")
            self.assertEqual(aggregate["course"], "swe-bench-lite")
            self.assertEqual(aggregate["run_count"], 2)
            comparison = aggregate["comparisons"][0]
            self.assertEqual(comparison["name"], "pi-vs-pi-fff")
            self.assertEqual(
                comparison["runs"],
                [
                    {
                        "index": 1,
                        "logbook": str(first),
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 1,
                                "resolution_rate": 1.0,
                                "tokens": 1000,
                                "cost": 0.001,
                                "duration_seconds": 10.0,
                                "tool_calls": 3,
                            },
                            {
                                "name": "pi-plus-fff",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 1,
                                "resolution_rate": 1.0,
                                "tokens": 2100,
                                "cost": 0.0021,
                                "duration_seconds": 11.1,
                                "tool_calls": 4,
                            },
                        ],
                        "delta": {
                            "baseline_vessel": "pi-baseline",
                            "challenger_vessel": "pi-plus-fff",
                            "resolved_instances_delta": 0,
                            "resolution_rate_delta": 0.0,
                            "tokens_delta": 1100,
                            "cost_delta": 0.0011,
                            "duration_seconds_delta": 1.1,
                            "tool_calls_delta": 1,
                        },
                    },
                    {
                        "index": 2,
                        "logbook": str(second),
                        "vessels": [
                            {
                                "name": "pi-baseline",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 0,
                                "resolution_rate": 0.0,
                                "tokens": 1000,
                                "cost": 0.001,
                                "duration_seconds": 10.0,
                                "tool_calls": 3,
                            },
                            {
                                "name": "pi-plus-fff",
                                "status": "measured",
                                "submitted_instances": 1,
                                "resolved_instances": 1,
                                "resolution_rate": 1.0,
                                "tokens": 2100,
                                "cost": 0.0021,
                                "duration_seconds": 11.1,
                                "tool_calls": 4,
                            },
                        ],
                        "delta": {
                            "baseline_vessel": "pi-baseline",
                            "challenger_vessel": "pi-plus-fff",
                            "resolved_instances_delta": 1,
                            "resolution_rate_delta": 1.0,
                            "tokens_delta": 1100,
                            "cost_delta": 0.0011,
                            "duration_seconds_delta": 1.1,
                            "tool_calls_delta": 1,
                        },
                    },
                ],
            )
            self.assertEqual(
                comparison["delta"],
                {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": "pi-plus-fff",
                    "resolved_instances_delta": 1,
                    "resolution_rate_delta": 0.5,
                    "tokens_delta": 2200,
                    "cost_delta": 0.0022,
                    "duration_seconds_delta": 2.2,
                    "tool_calls_delta": 2,
                },
            )
            self.assertEqual(
                comparison["delta_statistics"],
                {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": "pi-plus-fff",
                    "resolved_instances_delta": {
                        "runs": 2,
                        "mean": 0.5,
                        "stdev": 0.5,
                        "min": 0,
                        "max": 1,
                    },
                    "resolution_rate_delta": {
                        "runs": 2,
                        "mean": 0.5,
                        "stdev": 0.5,
                        "min": 0.0,
                        "max": 1.0,
                    },
                    "tokens_delta": {
                        "runs": 2,
                        "mean": 1100.0,
                        "stdev": 0.0,
                        "min": 1100,
                        "max": 1100,
                    },
                    "cost_delta": {
                        "runs": 2,
                        "mean": 0.0011,
                        "stdev": 0.0,
                        "min": 0.0011,
                        "max": 0.0011,
                    },
                    "duration_seconds_delta": {
                        "runs": 2,
                        "mean": 1.1,
                        "stdev": 0.0,
                        "min": 1.1,
                        "max": 1.1,
                    },
                    "tool_calls_delta": {
                        "runs": 2,
                        "mean": 1.0,
                        "stdev": 0.0,
                        "min": 1,
                        "max": 1,
                    },
                },
            )
            self.assertEqual(
                comparison["vessels"],
                [
                    {
                        "name": "pi-baseline",
                        "runs": 2,
                        "eligible_runs": 2,
                        "measured_runs": 2,
                        "submitted_instances": 2,
                        "resolved_instances": 1,
                        "resolution_rate": 0.5,
                        "usage_runs": 2,
                        "total_tokens": 2000,
                        "total_cost": 0.002,
                        "total_duration_seconds": 20.0,
                        "total_tool_calls": 6,
                        "statistics": {
                            "resolution_rate": {
                                "runs": 2,
                                "mean": 0.5,
                                "stdev": 0.5,
                                "min": 0.0,
                                "max": 1.0,
                            },
                            "tokens": {
                                "runs": 2,
                                "mean": 1000.0,
                                "stdev": 0.0,
                                "min": 1000,
                                "max": 1000,
                            },
                            "cost": {
                                "runs": 2,
                                "mean": 0.001,
                                "stdev": 0.0,
                                "min": 0.001,
                                "max": 0.001,
                            },
                            "duration_seconds": {
                                "runs": 2,
                                "mean": 10.0,
                                "stdev": 0.0,
                                "min": 10.0,
                                "max": 10.0,
                            },
                            "tool_calls": {
                                "runs": 2,
                                "mean": 3.0,
                                "stdev": 0.0,
                                "min": 3,
                                "max": 3,
                            },
                        },
                    },
                    {
                        "name": "pi-plus-fff",
                        "runs": 2,
                        "eligible_runs": 2,
                        "measured_runs": 2,
                        "submitted_instances": 2,
                        "resolved_instances": 2,
                        "resolution_rate": 1.0,
                        "usage_runs": 2,
                        "total_tokens": 4200,
                        "total_cost": 0.0042,
                        "total_duration_seconds": 22.2,
                        "total_tool_calls": 8,
                        "statistics": {
                            "resolution_rate": {
                                "runs": 2,
                                "mean": 1.0,
                                "stdev": 0.0,
                                "min": 1.0,
                                "max": 1.0,
                            },
                            "tokens": {
                                "runs": 2,
                                "mean": 2100.0,
                                "stdev": 0.0,
                                "min": 2100,
                                "max": 2100,
                            },
                            "cost": {
                                "runs": 2,
                                "mean": 0.0021,
                                "stdev": 0.0,
                                "min": 0.0021,
                                "max": 0.0021,
                            },
                            "duration_seconds": {
                                "runs": 2,
                                "mean": 11.1,
                                "stdev": 0.0,
                                "min": 11.1,
                                "max": 11.1,
                            },
                            "tool_calls": {
                                "runs": 2,
                                "mean": 4.0,
                                "stdev": 0.0,
                                "min": 4,
                                "max": 4,
                            },
                        },
                    },
                ],
            )

    def test_benchmark_aggregate_command_prints_text_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            second = _write_logbook(root / "run-2", baseline_resolved=0, fff_resolved=1)

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "internals",
                        "benchmark-aggregate",
                        "--logbook",
                        str(first),
                        "--logbook",
                        str(second),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn(
                "Benchmark aggregate: pi-fff-comparison / swe-bench-lite",
                report,
            )
            self.assertIn("Runs: 2", report)
            self.assertIn("Decision summary:", report)
            self.assertIn(
                (
                    "pi-vs-pi-fff | resolution better (+1 resolved, +0.500 rate) | "
                    "tokens worse (+2200) | cost worse (+0.002200) | "
                    "duration worse (+2.200s)"
                ),
                report,
            )
            self.assertIn("Aggregate deltas:", report)
            self.assertIn(
                "pi-vs-pi-fff | pi-baseline | pi-plus-fff | +1 | +0.500 | "
                "+2200 | +0.002200 | +2.200s | +2",
                report,
            )
            self.assertIn("Aggregate usage by vessel:", report)
            self.assertIn(
                "pi-vs-pi-fff | pi-plus-fff | 2 | 2 | 2 | 2 | 1.000 | "
                "2 | 4200 | 0.004200 | 22.200s | 8",
                report,
            )
            self.assertIn("Aggregate statistics by vessel:", report)
            self.assertIn(
                "pi-vs-pi-fff | pi-baseline | 0.500 | 0.000..1.000 | "
                "1000.0 | 1000..1000 | 0.001000 | 0.001000..0.001000 | "
                "10.000s | 10.000s..10.000s | 3.0 | 3..3",
                report,
            )
            self.assertIn("Aggregate variability by vessel:", report)
            self.assertIn(
                ("pi-vs-pi-fff | pi-baseline | 0.500 | 0.0 | 0.000000 | 0.000s | 0.0"),
                report,
            )
            self.assertIn("Aggregate delta statistics:", report)
            self.assertIn(
                "pi-vs-pi-fff | pi-baseline | pi-plus-fff | +0.500 | "
                "+0.000..+1.000 | +1100.0 | +1100..+1100 | +0.001100 | "
                "+0.001100..+0.001100 | +1.100s | +1.100s..+1.100s | "
                "+1.0 | +1..+1",
                report,
            )
            self.assertIn("Aggregate delta variability:", report)
            self.assertIn(
                (
                    "pi-vs-pi-fff | pi-baseline | pi-plus-fff | 0.5 | "
                    "0.500 | 0.0 | 0.000000 | 0.000s | 0.0"
                ),
                report,
            )
            self.assertIn("Aggregate runs by vessel:", report)
            self.assertIn(
                "pi-vs-pi-fff | 2 | pi-baseline | measured | 1 | 0 | 0.000 | "
                "1000 | 0.001000 | 10.000s | 3 |",
                report,
            )
            self.assertIn(
                "pi-vs-pi-fff | 2 | pi-plus-fff | measured | 1 | 1 | 1.000 | "
                "2100 | 0.002100 | 11.100s | 4 |",
                report,
            )

    def test_benchmark_aggregate_command_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _write_logbook(
                Path(temp_dir) / "run-1",
                baseline_resolved=1,
                fff_resolved=1,
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "internals",
                        "benchmark-aggregate",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-aggregate.v1")
            self.assertEqual(payload["run_count"], 1)

    def test_benchmark_aggregate_reports_missing_scorecard_without_traceback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "internals",
                        "benchmark-aggregate",
                        "--logbook",
                        str(Path(temp_dir) / "missing"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("benchmark scorecard artifact not found", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_benchmark_report_enriches_older_parent_aggregate_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _write_logbook(
                root / "series/runs/run-001",
                baseline_resolved=1,
                fff_resolved=1,
            )
            second = _write_logbook(
                root / "series/runs/run-002",
                baseline_resolved=0,
                fff_resolved=1,
            )
            parent = root / "series"
            aggregate = build_benchmark_aggregate([first, second])
            for comparison in aggregate["comparisons"]:
                del comparison["runs"]
            (parent / "benchmark-aggregate.json").write_text(
                json.dumps(aggregate) + "\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(parent),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn("Aggregate runs by vessel:", report)
            self.assertIn("series/runs/run-002", report)

    def test_benchmark_report_enriches_parent_aggregate_without_statistics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _write_logbook(
                root / "series/runs/run-001",
                baseline_resolved=1,
                fff_resolved=1,
            )
            second = _write_logbook(
                root / "series/runs/run-002",
                baseline_resolved=0,
                fff_resolved=1,
            )
            parent = root / "series"
            aggregate = build_benchmark_aggregate([first, second])
            for comparison in aggregate["comparisons"]:
                del comparison["delta_statistics"]
                for vessel in comparison["vessels"]:
                    del vessel["statistics"]
            (parent / "benchmark-aggregate.json").write_text(
                json.dumps(aggregate) + "\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(parent),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn("Aggregate statistics by vessel:", report)
            self.assertIn("Aggregate delta statistics:", report)

    def test_benchmark_report_enriches_parent_aggregate_without_stdev(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _write_logbook(
                root / "series/runs/run-001",
                baseline_resolved=1,
                fff_resolved=1,
            )
            second = _write_logbook(
                root / "series/runs/run-002",
                baseline_resolved=0,
                fff_resolved=1,
            )
            parent = root / "series"
            aggregate = build_benchmark_aggregate([first, second])
            for comparison in aggregate["comparisons"]:
                _remove_stdev(comparison["delta_statistics"])
                for vessel in comparison["vessels"]:
                    _remove_stdev(vessel["statistics"])
            (parent / "benchmark-aggregate.json").write_text(
                json.dumps(aggregate) + "\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(parent),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn("Aggregate variability by vessel:", report)
            self.assertIn("Aggregate delta variability:", report)
            self.assertIn(
                "pi-vs-pi-fff | pi-baseline | 0.500 | 0.0 | 0.000000 |",
                report,
            )

    def test_benchmark_aggregate_requires_compatible_regattas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            second = _write_logbook(root / "run-2", baseline_resolved=1, fff_resolved=1)
            scorecard_path = second / "benchmark-scorecard.json"
            scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
            scorecard["regatta"] = "other-regatta"
            scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "benchmark aggregate logbooks must share regatta",
            ):
                build_benchmark_aggregate([first, second])


def _write_logbook(
    logbook_dir: Path,
    *,
    baseline_resolved: int,
    fff_resolved: int,
) -> Path:
    logbook_dir.mkdir(parents=True)
    (logbook_dir / "benchmark-scorecard.json").write_text(
        json.dumps(_benchmark_scorecard(baseline_resolved, fff_resolved)) + "\n",
        encoding="utf-8",
    )
    (logbook_dir / "task-attempt-scorecard.json").write_text(
        json.dumps(_task_attempt_scorecard(baseline_resolved, fff_resolved)) + "\n",
        encoding="utf-8",
    )
    return logbook_dir


def _benchmark_scorecard(
    baseline_resolved: int, fff_resolved: int
) -> dict[str, object]:
    vessels = [
        _benchmark_vessel("pi-baseline", baseline_resolved),
        _benchmark_vessel("pi-plus-fff", fff_resolved),
    ]
    comparison = {
        "name": "pi-vs-pi-fff",
        "course": "swe-bench-lite",
        "summary": {
            "total_vessels": 2,
            "eligible_vessels": 2,
            "blocked_vessels": 0,
            "measured_vessels": 2,
            "missing_result_vessels": 0,
        },
        "delta": {
            "baseline_vessel": "pi-baseline",
            "challenger_vessel": "pi-plus-fff",
            "resolved_instances_delta": fff_resolved - baseline_resolved,
            "resolution_rate_delta": float(fff_resolved - baseline_resolved),
        },
        "vessels": vessels,
    }
    return {
        "schema": "yacht.benchmark-scorecard.v1",
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "adapter": {
            "kind": "swe-bench",
            "dataset": "princeton-nlp/SWE-bench_Lite",
            "split": "test",
        },
        "status": "complete",
        "summary": {
            "total_comparisons": 1,
            "total_vessels": 2,
            "eligible_vessels": 2,
            "blocked_vessels": 0,
            "measured_vessels": 2,
            "missing_result_vessels": 0,
        },
        "comparisons": [comparison],
    }


def _benchmark_vessel(name: str, resolved: int) -> dict[str, object]:
    unresolved = 1 - resolved
    return {
        "name": name,
        "status": "measured",
        "submitted_instances": 1,
        "resolved_instances": resolved,
        "resolution_rate": float(resolved),
        "resolved_ids": ["django__django-11099"] if resolved else [],
        "unresolved_ids": ["django__django-11099"] if unresolved else [],
        "eligible_for_benchmark": True,
        "preflight_status": "passed",
        "preflight_reason": "preflight-passed",
        "preflight_artifact_path": f"/tmp/{name}.json",
    }


def _task_attempt_scorecard(
    baseline_resolved: int,
    fff_resolved: int,
) -> dict[str, object]:
    vessels = [
        _task_attempt_vessel(
            "pi-baseline", tokens=1000, cost=0.001, duration=10.0, tools=3
        ),
        _task_attempt_vessel(
            "pi-plus-fff", tokens=2100, cost=0.0021, duration=11.1, tools=4
        ),
    ]
    return {
        "schema": "yacht.task-attempt-scorecard.v1",
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "status": "complete",
        "summary": _task_attempt_summary(vessels),
        "comparisons": [
            {
                "name": "pi-vs-pi-fff",
                "summary": _task_attempt_summary(vessels, total_vessels=2),
                "vessels": vessels,
            }
        ],
    }


def _task_attempt_vessel(
    name: str,
    *,
    tokens: int,
    cost: float,
    duration: float,
    tools: int,
) -> dict[str, object]:
    return {
        "name": name,
        "status": "measured",
        "task_attempts": 1,
        "completed_attempts": 1,
        "failed_attempts": 0,
        "success_rate": 1.0,
        "tool_call_count": tools,
        "tool_call_counts": {"tool": tools},
        "total_tokens": tokens,
        "total_cost": cost,
        "total_duration_seconds": duration,
        "artifact_paths": [f"/tmp/{name}/django__django-11099.json"],
    }


def _task_attempt_summary(
    vessels: list[dict[str, object]],
    *,
    total_vessels: int | None = None,
) -> dict[str, object]:
    return {
        "total_vessels": total_vessels or len(vessels),
        "total_attempts": len(vessels),
        "completed_attempts": len(vessels),
        "failed_attempts": 0,
        "total_tool_calls": sum(int(vessel["tool_call_count"]) for vessel in vessels),
        "tool_call_counts": {
            "tool": sum(int(vessel["tool_call_count"]) for vessel in vessels)
        },
        "total_tokens": sum(int(vessel["total_tokens"]) for vessel in vessels),
        "total_cost": sum(float(vessel["total_cost"]) for vessel in vessels),
        "total_duration_seconds": sum(
            float(vessel["total_duration_seconds"]) for vessel in vessels
        ),
        "total_comparisons": 1,
    }


def _remove_stdev(statistics: dict[str, object]) -> None:
    for value in statistics.values():
        if isinstance(value, dict):
            value.pop("stdev", None)


if __name__ == "__main__":
    unittest.main()
