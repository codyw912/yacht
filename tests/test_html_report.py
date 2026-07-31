import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.logbook.io import write_json
from yacht.reports.benchmark_aggregate import build_benchmark_aggregate
from yacht.reports.html_report import (
    render_benchmark_aggregate_html,
    render_benchmark_html,
    render_smoke_html,
)


def _scorecard(
    *,
    resolved_delta: int = 0,
    rate_delta: float = 0.0,
    submitted: int = 1,
    challenger: str = "pi-plus-tool",
) -> dict:
    def vessel(name: str, resolved: int) -> dict:
        return {
            "name": name,
            "preflight_status": "passed",
            "preflight_reason": "preflight-passed",
            "preflight_artifact_path": f"logbook/preflight/{name}.json",
            "status": "measured",
            "eligible_for_benchmark": True,
            "resolved_instances": resolved,
            "submitted_instances": submitted,
            "resolution_rate": resolved / submitted if submitted else 0.0,
            "resolved_ids": [f"task-{index}" for index in range(resolved)],
            "unresolved_ids": [f"task-{index}" for index in range(resolved, submitted)],
        }

    vessel_counts = {
        "total_vessels": 2,
        "eligible_vessels": 2,
        "blocked_vessels": 0,
        "measured_vessels": 2,
        "missing_result_vessels": 0,
    }
    return {
        "schema": "yacht.benchmark-scorecard.v1",
        "regatta": "tool-claim-check",
        "course": "swe-bench-lite",
        "adapter": {
            "kind": "swe-bench",
            "dataset": "princeton-nlp/SWE-bench_Lite",
            "split": "test",
        },
        "status": "complete",
        "summary": {"total_comparisons": 1, **vessel_counts},
        "comparisons": [
            {
                "name": "baseline-vs-tool",
                "course": "swe-bench-lite",
                "summary": dict(vessel_counts),
                "delta": {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": challenger,
                    "resolved_instances_delta": resolved_delta,
                    "resolution_rate_delta": rate_delta,
                },
                "vessels": [
                    vessel("pi-baseline", 1),
                    vessel(challenger, 1 + resolved_delta),
                ],
            }
        ],
        "next_steps": [],
    }


def _attempts() -> dict:
    return {
        "schema": "yacht.task-attempt-scorecard.v1",
        "regatta": "tool-claim-check",
        "course": "swe-bench-lite",
        "status": "complete",
        "summary": {
            "total_comparisons": 1,
            "total_vessels": 2,
            "total_attempts": 2,
            "completed_attempts": 2,
            "failed_attempts": 0,
            "total_tokens": 1800,
            "total_cost": 0.018,
            "total_duration_seconds": 105.0,
            "total_distinct_tool_uses": 7,
            "attempts_by_tool": {"bash": 4, "newtool": 3},
        },
        "comparisons": [
            {
                "name": "baseline-vs-tool",
                "summary": {
                    "total_vessels": 2,
                    "total_attempts": 2,
                    "completed_attempts": 2,
                    "failed_attempts": 0,
                    "total_tokens": 1800,
                    "total_cost": 0.018,
                    "total_duration_seconds": 105.0,
                    "total_distinct_tool_uses": 7,
                    "attempts_by_tool": {"bash": 4, "newtool": 3},
                },
                "vessels": [
                    {
                        "name": "pi-baseline",
                        "status": "measured",
                        "task_attempts": 1,
                        "completed_attempts": 1,
                        "failed_attempts": 0,
                        "success_rate": 1.0,
                        "harnesses": ["pi"],
                        "artifact_paths": ["logbook/task-attempts/a.json"],
                        "total_tokens": 1000,
                        "total_cost": 0.01,
                        "total_duration_seconds": 60.0,
                        "distinct_tool_uses": 2,
                        "attempts_by_tool": {"bash": 2},
                    },
                    {
                        "name": "pi-plus-tool",
                        "status": "measured",
                        "task_attempts": 1,
                        "completed_attempts": 1,
                        "failed_attempts": 0,
                        "success_rate": 1.0,
                        "harnesses": ["pi"],
                        "artifact_paths": ["logbook/task-attempts/b.json"],
                        "total_tokens": 800,
                        "total_cost": 0.008,
                        "total_duration_seconds": 45.0,
                        "distinct_tool_uses": 5,
                        "attempts_by_tool": {"bash": 2, "newtool": 3},
                    },
                ],
            }
        ],
    }


class BenchmarkHtmlTests(unittest.TestCase):
    def test_tied_verdict_with_small_sample_badge(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertIn("tied with", html)
        self.assertIn("small sample", html)
        self.assertIn('class="verdict tied"', html)

    def test_improved_verdict_without_badge_on_larger_sample(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(resolved_delta=2, rate_delta=0.4, submitted=5),
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn('class="verdict improved"', html)
        self.assertIn("resolved 2 more", html)
        self.assertNotIn("small sample", html)

    def test_regressed_verdict(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(resolved_delta=-1, rate_delta=-0.2, submitted=5),
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn('class="verdict regressed"', html)
        self.assertIn("resolved 1 fewer", html)

    def test_tool_call_evidence_table_lists_challenger_tool(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertIn("newtool", html)
        self.assertIn("actually", html)

    def test_escapes_untrusted_names(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(challenger="pi-<script>alert(1)</script>"),
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_contains_no_external_references(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


def _aggregate(
    *,
    mean: float,
    stdev: float,
    run_count: int = 3,
    delta_stats_extra: dict | None = None,
) -> dict:
    return {
        "schema": "yacht.benchmark-aggregate.v1",
        "regatta": "tool-claim-check",
        "course": "swe-bench-lite",
        "run_count": run_count,
        "logbooks": [f"/tmp/run-{index}" for index in range(run_count)],
        "comparisons": [
            {
                "name": "baseline-vs-tool",
                "baseline": "pi-baseline",
                "challenger": "pi-plus-tool",
                "vessels": [
                    {
                        "name": name,
                        "runs": run_count,
                        "measured_runs": run_count,
                        "submitted_instances": run_count * 2,
                        "resolved_instances": run_count,
                        "resolution_rate": 0.5,
                        "total_tokens": 3000,
                        "total_cost": 0.03,
                        "total_duration_seconds": 180.0,
                        "total_distinct_tool_uses": 6,
                        "statistics": {
                            "resolution_rate": {
                                "runs": run_count,
                                "mean": 0.5,
                                "stdev": 0.1,
                            },
                            "tokens": {"runs": run_count, "mean": 1000, "stdev": 50},
                            "cost": {"runs": run_count, "mean": 0.01, "stdev": 0.001},
                            "duration_seconds": {
                                "runs": run_count,
                                "mean": 60.0,
                                "stdev": 5.0,
                            },
                            "tool_calls": {"runs": run_count, "mean": 2, "stdev": 0},
                        },
                    }
                    for name in ("pi-baseline", "pi-plus-tool")
                ],
                "runs": [
                    {
                        "index": index + 1,
                        "logbook": f"/tmp/run-{index}",
                        "vessels": [],
                        "delta": {
                            "resolved_instances_delta": 1,
                            "resolution_rate_delta": 0.5,
                            "tokens_delta": -100,
                        },
                    }
                    for index in range(run_count)
                ],
                "delta": {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": "pi-plus-tool",
                    "resolved_instances_delta": 2,
                    "resolution_rate_delta": 0.333,
                },
                "delta_statistics": {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": "pi-plus-tool",
                    "resolved_instances_delta": {
                        "runs": run_count,
                        "mean": mean,
                        "stdev": stdev,
                        **(delta_stats_extra or {}),
                    },
                },
            }
        ],
    }


class AggregateHtmlTests(unittest.TestCase):
    def test_consistent_runs_get_good_badge(self) -> None:
        html = render_benchmark_aggregate_html(_aggregate(mean=1.0, stdev=0.0))

        self.assertIn("consistent across 3 runs", html)
        self.assertIn('class="badge good"', html)

    def test_delta_within_variance_gets_warning_badge(self) -> None:
        html = render_benchmark_aggregate_html(_aggregate(mean=0.3, stdev=0.8))

        self.assertIn("within run-to-run variance", html)

    def test_delta_exceeding_variance_gets_good_badge(self) -> None:
        html = render_benchmark_aggregate_html(_aggregate(mean=1.5, stdev=0.5))

        self.assertIn("exceeds run variance", html)

    def test_single_run_notes_missing_variance_estimate(self) -> None:
        html = render_benchmark_aggregate_html(
            _aggregate(mean=1.0, stdev=0.0, run_count=1)
        )

        self.assertIn("single run: observation only, no evidence estimate", html)

    def test_graded_difference_renders_evidence_badge(self) -> None:
        html = render_benchmark_aggregate_html(
            _aggregate(
                mean=1.0,
                stdev=0.2,
                delta_stats_extra={
                    "grade": "evidence-of-difference",
                    "interval": {"mean": 1.0, "low": 0.5, "high": 1.5},
                },
            )
        )

        self.assertIn("evidence of difference", html)
        self.assertIn("95% CI +0.50", html)
        self.assertIn('class="badge good"', html)

    def test_graded_noise_renders_not_distinguishable_badge(self) -> None:
        html = render_benchmark_aggregate_html(
            _aggregate(
                mean=0.5,
                stdev=0.5,
                delta_stats_extra={
                    "grade": "not-distinguishable",
                    "interval": {"mean": 0.5, "low": -5.85, "high": 6.85},
                },
            )
        )

        self.assertIn("not distinguishable from run-to-run variation", html)

    def test_per_run_delta_rows_render(self) -> None:
        html = render_benchmark_aggregate_html(_aggregate(mean=1.0, stdev=0.0))

        self.assertIn("Per-run deltas", html)
        self.assertIn("/tmp/run-2", html)

    def test_real_aggregate_builder_output_renders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbooks = []
            for index, delta in enumerate((0, 1)):
                logbook_dir = root / f"run-{index}"
                write_json(
                    logbook_dir / "benchmark-scorecard.json",
                    _scorecard(
                        resolved_delta=delta,
                        rate_delta=delta / 2,
                        submitted=2,
                    ),
                )
                write_json(logbook_dir / "task-attempt-scorecard.json", _attempts())
                logbooks.append(logbook_dir)

            aggregate = build_benchmark_aggregate(logbooks)
            html = render_benchmark_aggregate_html(aggregate)

        self.assertIn("<!doctype html>", html)
        self.assertIn("2 repeated runs", html)
        self.assertIn("pi-plus-tool", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


class SmokeHtmlTests(unittest.TestCase):
    def test_renders_artifact_checklist(self) -> None:
        html = render_smoke_html(
            smoke_status={
                "status": "ready",
                "artifacts": [
                    {
                        "name": "run-index",
                        "path": "logbook/run-index.json",
                        "present": True,
                    },
                    {"name": "scorecard", "path": "logbook/x.json", "present": False},
                ],
                "next_step": "uv run yacht report --logbook logbook",
            },
            logbook_dir=Path("logbook"),
        )

        self.assertIn("Smoke status: ready", html)
        self.assertIn("present", html)
        self.assertIn("missing", html)
        self.assertIn("yacht report", html)


class HtmlReportCommandTests(unittest.TestCase):
    def test_report_html_writes_benchmark_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            output_path = Path(temp_dir) / "report.html"
            write_json(
                logbook_dir / "run-index.json",
                {"schema": "yacht.run-index.v1", "run_kind": "real-benchmark"},
            )
            write_json(logbook_dir / "benchmark-scorecard.json", _scorecard())

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "html",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            html = output_path.read_text(encoding="utf-8")
            self.assertTrue(html.startswith("<!doctype html>"))
            self.assertIn("tool-claim-check", html)

    def test_report_html_rejects_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_json(
                logbook_dir / "run-index.json",
                {"schema": "yacht.run-index.v1", "run_kind": "real-benchmark"},
            )
            write_json(logbook_dir / "benchmark-scorecard.json", _scorecard())
            stderr = StringIO()

            from contextlib import redirect_stderr

            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "html",
                        "--vessel",
                        "pi-baseline",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("html report always includes", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()


def _invocation(*, invoked: int = 1, status: str = "measured") -> dict:
    entry = {
        "tool": "team-conventions",
        "kind": "agent-skill",
        "expected_calls": ["Skill:team-conventions"],
        "attempts": 1,
        "measured_attempts": 1 if status == "measured" else 0,
        "status": status,
    }
    if status == "measured":
        entry.update(
            {
                "invoked_attempts": invoked,
                "invocation_rate": float(invoked),
                "invocation_interval": {"low": 0.2, "high": 1.0},
                "completed_attempts": 1,
                "invoked_completed_attempts": invoked,
                "completed_invocation_rate": float(invoked),
                "completed_invocation_interval": {"low": 0.2, "high": 1.0},
            }
        )
    return entry


class DecisionMetricsParityTests(unittest.TestCase):
    def test_evidence_grade_renders_as_badge(self) -> None:
        scorecard = _scorecard(resolved_delta=1, rate_delta=1.0)
        scorecard["comparisons"][0]["statistics"] = {
            "confidence_level": 0.95,
            "paired": {
                "grade": "insufficient-evidence",
                "discordant_baseline_only": 0,
                "discordant_challenger_only": 1,
                "min_significant_discordant": 6,
                "p_value": 1.0,
                "shared_tasks": 1,
            },
        }

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn("insufficient evidence: observation only", html)

    def test_recorded_baseline_renders_badge_and_stored_usage(self) -> None:
        scorecard = _scorecard()
        recorded = scorecard["comparisons"][0]["vessels"][0]
        recorded["status"] = "recorded"
        for key in (
            "preflight_status",
            "preflight_reason",
            "preflight_artifact_path",
            "eligible_for_benchmark",
        ):
            recorded.pop(key)
        recorded["baseline_source"] = {
            "logbook": "/tmp/recorded",
            "vessel": "pi-baseline",
            "run_date": "2026-07-26T20:08:37Z",
            "usage": {"total_tokens": 92153, "total_cost": 0.022},
        }

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn("recorded baseline from 2026-07-26", html)
        self.assertIn('<span class="muted">recorded</span>', html)
        self.assertIn("92,153", html)

    def test_delivery_badge_table_and_confound_note_render(self) -> None:
        scorecard = _scorecard(resolved_delta=1, rate_delta=0.5)
        scorecard["comparisons"][0]["delivery"] = {
            "vessel": "pi-plus-tool",
            "status": "delivered",
            "tools": [_invocation()],
        }
        attempts = _attempts()
        attempts["comparisons"][0]["vessels"][1]["tool_invocations"] = [_invocation()]
        attempts["comparisons"][0]["vessels"][1]["usage_sources"] = ["reported"]

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=attempts,
            logbook_dir=Path("logbook"),
        )

        self.assertIn("treatment delivered", html)
        self.assertIn("Skill delivery", html)
        self.assertIn("Skill:team-conventions", html)
        self.assertIn("Outcome-confounded", html)
        self.assertIn("Tokens/res", html)
        self.assertIn("reported", html)

    def test_not_delivered_renders_bad_badge(self) -> None:
        scorecard = _scorecard(resolved_delta=1, rate_delta=0.5)
        scorecard["comparisons"][0]["delivery"] = {
            "vessel": "pi-plus-tool",
            "status": "not-delivered",
            "tools": [_invocation(invoked=0)],
        }

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn('<span class="badge bad">treatment NOT delivered</span>', html)

    def test_aggregate_vessel_table_renders_delivery_column(self) -> None:
        aggregate = _aggregate(mean=1.0, stdev=0.0)
        aggregate["comparisons"][0]["vessels"][1]["tool_invocations"] = [
            _invocation(invoked=1)
        ]

        html = render_benchmark_aggregate_html(aggregate)

        self.assertIn("Delivery", html)
        self.assertIn("team-conventions: 1/1", html)

    def test_recorded_baseline_usage_feeds_usage_chart(self) -> None:
        scorecard = _scorecard()
        recorded = scorecard["comparisons"][0]["vessels"][0]
        recorded["status"] = "recorded"
        for key in (
            "preflight_status",
            "preflight_reason",
            "preflight_artifact_path",
            "eligible_for_benchmark",
        ):
            recorded.pop(key)
        recorded["baseline_source"] = {
            "logbook": "/tmp/recorded",
            "vessel": "pi-baseline",
            "usage": {
                "total_tokens": 92153,
                "total_cost": 0.022,
                "total_duration_seconds": 52.4,
                "distinct_tool_uses": 3,
            },
        }
        attempts = _attempts()
        attempts["comparisons"][0]["vessels"] = attempts["comparisons"][0]["vessels"][
            1:
        ]

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=attempts,
            logbook_dir=Path("logbook"),
        )

        chart = html[html.index("<svg") : html.index("</svg>")]
        self.assertIn("pi-baseline", chart)
        self.assertIn("92,153", chart)

    def test_tool_call_headers_keep_qualified_names_lowercase(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertIn('<th class="num"><code>newtool</code></th>', html)
        self.assertIn("th code { text-transform: none;", html)

    def test_repetition_budget_renders_with_optional_stopping_warning(self) -> None:
        scorecard = _scorecard(resolved_delta=1, rate_delta=0.5)
        scorecard["comparisons"][0]["statistics"] = {
            "confidence_level": 0.95,
            "paired": {"grade": "insufficient-evidence", "p_value": 1.0},
            "repetition_guidance": {
                "power_target": 0.8,
                "significance_level": 0.05,
                "observed_discordance_rate": 0.7,
                "shared_tasks_per_run": 10,
                "applies_to": "a fresh run committed to in advance",
                "plans": [
                    {
                        "assumed_favored_fraction": 0.9,
                        "discordant_pairs_needed": 12,
                        "repetitions": 2,
                        "repetitions_range": {"low": 2, "high": 4},
                    },
                    {
                        "assumed_favored_fraction": 0.55,
                        "discordant_pairs_needed": None,
                    },
                ],
            },
        }

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn("Repetition budget", html)
        self.assertIn("challenger wins 90% of discordant pairs", html)
        self.assertIn("optional stopping", html)
        self.assertIn("unreachable", html)

    def test_no_repetition_budget_when_evidence_was_found(self) -> None:
        scorecard = _scorecard(resolved_delta=1, rate_delta=0.5)
        scorecard["comparisons"][0]["statistics"] = {
            "confidence_level": 0.95,
            "paired": {"grade": "evidence-of-difference", "p_value": 0.01},
        }

        html = render_benchmark_html(
            scorecard=scorecard,
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertNotIn("Repetition budget", html)
